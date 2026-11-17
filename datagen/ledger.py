"""Column-oriented ledger builder with double entry and running balances.

Factories and scenarios append events here (vectorised batches or single
rows). ``finalize`` sorts per account, derives opening balances so no balance
goes negative, computes ``balance_after`` and assigns ``transfer_id``s in time
order (so ids carry no hint of which generator produced them). Both sides of a
transfer between two bank accounts share one group key and one ``transfer_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from datagen.timebase import HOUR_S

COLUMNS = ("account", "ts", "sign", "paise", "channel", "cp_type", "cp_ref", "cp_name", "remarks", "group")

CREDIT = 1
DEBIT = -1


@dataclass
class FinalLedger:
    """Sorted ledger columns plus derived balances and ids."""

    cols: dict[str, np.ndarray]
    balance_after: np.ndarray
    transfer_ids: np.ndarray
    opening: dict[str, int]

    def __len__(self) -> int:
        return len(self.cols["ts"])


@dataclass
class LedgerBuilder:
    """Accumulates ledger rows before balances are known."""

    _chunks: list[dict[str, Any]] = field(default_factory=list)
    _rows: list[tuple[Any, ...]] = field(default_factory=list)
    _next_group: int = 0

    def new_groups(self, n: int) -> np.ndarray:
        """Reserve ``n`` transfer group keys."""
        out = np.arange(self._next_group, self._next_group + n, dtype=np.int64)
        self._next_group += n
        return out

    def add_batch(self, **cols: Any) -> None:
        """Append a vectorised batch; every column must have the same length."""
        lengths = {len(v) for v in cols.values()}
        if len(lengths) != 1:
            raise ValueError(f"batch columns differ in length: {lengths}")
        if lengths == {0}:
            return
        missing = set(COLUMNS) - cols.keys()
        if missing:
            raise ValueError(f"batch missing columns: {sorted(missing)}")
        self._chunks.append(cols)

    def add(
        self,
        account: str,
        ts: int,
        sign: int,
        paise: int,
        channel: str,
        cp_type: str,
        cp_ref: str | None,
        cp_name: str | None,
        remarks: str | None,
        group: int | None = None,
    ) -> int:
        """Append one row; returns its group key."""
        g = int(self.new_groups(1)[0]) if group is None else group
        self._rows.append((account, int(ts), sign, int(paise), channel, cp_type, cp_ref, cp_name, remarks, g))
        return g

    def add_internal(
        self,
        src: str,
        dst: str,
        ts: int,
        paise: int,
        channel: str,
        src_name: str,
        dst_name: str,
        remarks_out: str,
        remarks_in: str,
        lag_s: int = 5,
    ) -> int:
        """Append both sides of a transfer between two bank accounts."""
        g = int(self.new_groups(1)[0])
        self.add(src, ts, DEBIT, paise, channel, "account", dst, dst_name, remarks_out, g)
        self.add(dst, ts + lag_s, CREDIT, paise, channel, "account", src, src_name, remarks_in, g)
        return g

    def net_before(self, account: str, before_ts: int) -> int:
        """Signed paise of ``account``'s rows so far with ``ts < before_ts``."""
        total = 0
        for chunk in self._chunks:
            acct = np.asarray(chunk["account"], dtype=object)
            mask = (acct == account) & (np.asarray(chunk["ts"], dtype=np.int64) < before_ts)
            if mask.any():
                total += int((np.asarray(chunk["sign"], dtype=np.int64)[mask] * np.asarray(chunk["paise"], dtype=np.int64)[mask]).sum())
        for row in self._rows:
            if row[0] == account and row[1] < before_ts:
                total += row[2] * row[3]
        return total

    def _concat(self) -> dict[str, np.ndarray]:
        parts: list[dict[str, np.ndarray]] = []
        for chunk in self._chunks:
            parts.append({c: np.asarray(chunk[c], dtype=object if c not in ("ts", "sign", "paise", "group") else np.int64) for c in COLUMNS})
        if self._rows:
            cols = list(zip(*self._rows, strict=True))
            parts.append(
                {
                    c: np.asarray(cols[i], dtype=object if c not in ("ts", "sign", "paise", "group") else np.int64)
                    for i, c in enumerate(COLUMNS)
                }
            )
        return {c: np.concatenate([p[c] for p in parts]) for c in COLUMNS}

    def finalize(
        self,
        base_opening: dict[str, int],
        opened_in_dataset: dict[str, int],
        deposit_name: str,
    ) -> FinalLedger:
        """Sort, derive opening balances and running balances, assign ids.

        Args:
            base_opening: Desired opening balance (paise) for accounts that
                existed before the dataset started.
            opened_in_dataset: Account -> opened_at epoch for accounts opened
                inside the dataset; their opening balance is zero and an
                initial cash deposit is added when activity would go negative.
            deposit_name: Counterparty name shown on initial deposits.

        Returns:
            The finalised ledger.
        """
        for _ in range(2):
            cols = self._concat()
            order = np.lexsort((cols["group"], cols["ts"], cols["account"]))
            cols = {c: v[order] for c, v in cols.items()}
            signed = cols["sign"] * cols["paise"]
            accounts = cols["account"]
            starts = np.r_[0, np.flatnonzero(accounts[1:] != accounts[:-1]) + 1]
            lengths = np.diff(np.r_[starts, len(accounts)])
            cum = np.cumsum(signed)
            offsets = np.repeat(np.r_[0, cum[starts[1:] - 1]], lengths)
            running = cum - offsets
            mins = np.minimum.reduceat(running, starts)
            firsts = cols["ts"][starts]
            needs_deposit = False
            opening: dict[str, int] = {}
            for acct, low, first in zip(accounts[starts], mins, firsts, strict=True):
                need = max(0, -int(low))
                if acct in opened_in_dataset:
                    if need > 0:
                        # Realistic: new accounts are opened with a cash deposit.
                        amount = need + 50_000
                        self.add(acct, int(first) - HOUR_S, CREDIT, amount, "cash_deposit", "cash", None, deposit_name, "Cash deposit at account opening")
                        needs_deposit = True
                    opening[acct] = 0
                else:
                    opening[acct] = max(base_opening.get(acct, 0), need + 100_000)
            if not needs_deposit:
                break
        open_arr = np.repeat(np.array([opening[a] for a in accounts[starts]], dtype=np.int64), lengths)
        balance_after = open_arr + running

        # transfer ids in time order of each group's first row
        groups = cols["group"]
        uniq, first_idx = np.unique(groups, return_index=True)
        rank_order = np.lexsort((uniq, cols["ts"][first_idx]))
        rank = np.empty(len(uniq), dtype=np.int64)
        rank[rank_order] = np.arange(len(uniq))
        pos = np.searchsorted(uniq, groups)
        transfer_ids = np.array([f"TRF{r:010d}" for r in rank[pos]], dtype=object)
        return FinalLedger(cols=cols, balance_after=balance_after, transfer_ids=transfer_ids, opening=opening)

"""Scenario base class, registry and shared flow helpers.

A scenario plants one alert-worthy account with hidden ground truth. Each
class is parametrised by variants from ``config/scenarios.yaml`` and registered
with ``@register_scenario``; adding a scenario never edits existing code.

Flow helpers build the 14-day window activity on top of a persona backstory:
``fan_in`` (many credits from many senders) and ``sweep`` (outflows after a
delay, to beneficiaries, ATMs or wallets, split into realistic chunks).
"""

from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from datagen.context import Account, GenContext
from datagen.factories.background import PersonaEngine, create_persona_account
from datagen.factories.personas import HOUR_CURVES, PERSONAS
from datagen.ledger import CREDIT, DEBIT
from datagen.timebase import DAY_S, HOUR_S, IST_OFFSET_S, MINUTE_S

_REGISTRY: dict[str, type[Scenario]] = {}


def register_scenario(cls: type[Scenario]) -> type[Scenario]:
    """Class decorator that registers a scenario under ``cls.name``."""
    _REGISTRY[cls.name] = cls
    return cls


def registered_scenarios() -> dict[str, type[Scenario]]:
    return dict(_REGISTRY)


@dataclass
class Credit:
    """One planted inbound transfer."""

    ts: int
    paise: int
    sender: str
    group: int


class Scenario(ABC):
    """Base class: ``build`` plants one account for ``variant``."""

    name: ClassVar[str]

    def __init__(self, ctx: GenContext, params: dict[str, Any]) -> None:
        self.ctx = ctx
        self.params = params
        self.engine = PersonaEngine(ctx)

    @abstractmethod
    def build(self, variant: str, ordinal: int) -> Account:
        """Create the account, its backstory and window activity; record truth."""

    # --- shared helpers -------------------------------------------------------

    @property
    def rng(self) -> np.random.Generator:
        return self.ctx.rng

    def vp(self, variant: str) -> dict[str, Any]:
        """Parameters of ``variant``."""
        return dict(self.params["variants"][variant])

    def rint(self, bounds: Sequence[int]) -> int:
        return int(self.rng.integers(int(bounds[0]), int(bounds[1]) + 1))

    def runif(self, bounds: Sequence[float]) -> float:
        return float(self.rng.uniform(float(bounds[0]), float(bounds[1])))

    def account(self, persona: str, *, opened_days_before_window: Sequence[int] | None = None, occupation: str | None = None, declared_turnover: int | None = None) -> Account:
        tb = self.ctx.tb
        opened = None
        if opened_days_before_window is not None:
            opened = tb.window_start_ts - self.rint(opened_days_before_window) * DAY_S
        acct = create_persona_account(self.ctx, PERSONAS[persona], opened_ts=opened, occupation=occupation)
        if declared_turnover is not None:
            acct.declared_turnover = declared_turnover
        return acct

    def backstory(self, acct: Account, persona: str, *, until_window_end: bool = True, scale: float = 1.0) -> None:
        tb = self.ctx.tb
        start = max(acct.opened_ts, tb.dataset_start_ts)
        end = tb.end_ts if until_window_end else tb.window_start_ts
        income = self.ctx.customers[acct.customer_id].declared_income / 12.0
        self.engine.generate(PERSONAS[persona], [acct], np.asarray([start]), np.asarray([end]), np.asarray([scale]), np.asarray([income]), allow_internal=False)

    def times(self, n: int, start: int, end: int, hours: str = "spread") -> np.ndarray:
        """``n`` sorted timestamps in ``[start, end)`` following an hour curve."""
        w = np.asarray(HOUR_CURVES[hours], dtype=float)
        days = self.rng.integers(0, max((end - start) // DAY_S, 1), size=n)
        day0 = start - ((start + IST_OFFSET_S) % DAY_S)
        ts = day0 + days * DAY_S + self.rng.choice(24, size=n, p=w / w.sum()) * HOUR_S + self.rng.integers(0, HOUR_S, size=n)
        ts = np.clip(ts, start, end - MINUTE_S)
        return np.sort(ts)

    def amounts(self, n: int, median: float, sigma: float, round_to: int = 0, p_round: float = 0.0, cap: float | None = None) -> np.ndarray:
        rupees = median * self.rng.lognormal(0.0, sigma, size=n)
        if cap:
            rupees = np.minimum(rupees, cap)
        if round_to:
            rounded = np.maximum(np.round(rupees / round_to) * round_to, round_to)
            rupees = np.where(self.rng.random(n) < p_round, rounded, np.round(rupees))
        return np.round(rupees).astype(np.int64) * 100

    def fan_in(
        self,
        acct: Account,
        senders: Sequence[str],
        n_credits: int,
        start: int,
        end: int,
        median: float,
        sigma: float,
        remarks: Callable[[str], str],
        *,
        channels: Sequence[str] = ("upi", "imps"),
        round_to: int = 0,
        p_round: float = 0.0,
        hours: str = "spread",
        cap: float | None = 95_000,
    ) -> list[Credit]:
        """Plant ``n_credits`` credits from ``senders`` (each sender at least once)."""
        n = max(n_credits, len(senders))
        order = list(senders) + [senders[int(i)] for i in self.rng.integers(0, len(senders), size=n - len(senders))]
        order = [order[int(i)] for i in self.rng.permutation(n)]
        ts = self.times(n, start, end, hours)
        paise = self.amounts(n, median, sigma, round_to, p_round, cap)
        out: list[Credit] = []
        for t, p, s in zip(ts, paise, order, strict=True):
            channel = str(self.rng.choice(list(channels)))
            g = self.ctx.ledger.add(acct.id, int(t), CREDIT, int(p), channel, "counterparty", s, self.ctx.cp_name(s), remarks(s)[:140])
            out.append(Credit(int(t), int(p), s, g))
        return out

    def sweep(
        self,
        acct: Account,
        credits: Sequence[Credit],
        *,
        delay_min: Sequence[float],
        fraction: Sequence[float],
        keep_paise: int,
        beneficiaries: Sequence[tuple[str, str | None]],
        weights: Sequence[float],
        chunk_paise: dict[str, int],
        remark: Callable[[str, str | None], str],
        min_paise: int = 50_000,
        end: int | None = None,
        sweep_existing: bool = False,
    ) -> int:
        """Move money out after each credit; returns total paise swept.

        Beneficiary kinds: ``("cp", cp_id)`` external transfer, ``("atm", None)``,
        ``("wallet", cp_id)`` wallet load, ``("account", acct_id)`` internal.
        """
        ctx, rng = self.ctx, self.rng
        limit = end or ctx.tb.end_ts
        events: list[tuple[int, int, int]] = []  # (ts, kind 0=credit 1=sweep, paise)
        for c in credits:
            heapq.heappush(events, (c.ts, 0, c.paise))
            heapq.heappush(events, (c.ts + int(self.runif(delay_min) * MINUTE_S), 1, 0))
        balance = 0
        if sweep_existing and credits:
            # Mules empty the whole account, not just the new money.
            first = min(c.ts for c in credits)
            balance = ctx.base_opening.get(acct.id, 0) + ctx.ledger.net_before(acct.id, first)
            balance = max(balance, 0)
        total = 0
        w = np.asarray(weights, dtype=float) / sum(weights)
        while events:
            ts, kind, paise = heapq.heappop(events)
            if kind == 0:
                balance += paise
                continue
            amount = int((balance - keep_paise) * self.runif(fraction))
            if amount < min_paise or ts >= limit:
                continue
            bkind, ref = beneficiaries[int(rng.choice(len(beneficiaries), p=w))]
            chunk = chunk_paise.get(bkind, amount)
            parts = [chunk] * (amount // chunk) + ([amount % chunk] if amount % chunk >= 10_000 else [])
            for k, part in enumerate(parts):
                t = min(ts + k * int(rng.integers(2, 6)) * MINUTE_S, limit - MINUTE_S)
                part = part // 100 * 100
                self._out(acct, t, part, bkind, ref, remark(bkind, ref))
                balance -= part
                total += part
        return total

    def _out(self, acct: Account, ts: int, paise: int, kind: str, ref: str | None, remarks: str) -> None:
        ctx = self.ctx
        if kind == "atm":
            city = ctx.customers[acct.customer_id].city
            ctx.ledger.add(acct.id, ts, DEBIT, paise, "atm", "atm", None, f"ATM {city}", remarks)
        elif kind == "wallet":
            assert ref is not None
            ctx.ledger.add(acct.id, ts, DEBIT, paise, "wallet_load", "counterparty", ref, ctx.cp_name(ref), remarks)
        elif kind == "account":
            assert ref is not None
            dst = ctx.accounts[ref]
            ctx.ledger.add_internal(acct.id, dst.id, ts, paise, "imps", acct.holder_name, dst.holder_name, remarks, remarks)
        else:
            assert ref is not None
            channel = "neft" if paise > 20_000_000 else str(self.rng.choice(["imps", "upi"] if paise <= 10_000_000 else ["imps", "neft"]))
            ctx.ledger.add(acct.id, ts, DEBIT, paise, channel, "counterparty", ref, ctx.cp_name(ref), remarks)

    def pay(self, acct: Account, ts: int, paise: int, cp: str, channel: str, remarks: str) -> int:
        return self.ctx.ledger.add(acct.id, ts, DEBIT, paise, channel, "counterparty", cp, self.ctx.cp_name(cp), remarks[:140])

    def receive(self, acct: Account, ts: int, paise: int, cp: str, channel: str, remarks: str) -> int:
        return self.ctx.ledger.add(acct.id, ts, CREDIT, paise, channel, "counterparty", cp, self.ctx.cp_name(cp), remarks[:140])

    def ref(self) -> str:
        return self.ctx.names.upi_ref()

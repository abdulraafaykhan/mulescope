"""Post-generation sanity checks (section 6.3).

Run in memory on the finalised ledger before anything is written, plus an
alert-coverage check after the detector runs. Problems are returned as
strings; ``cli.py`` prints them and fails loudly on hard errors.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from datagen.context import GenContext
from datagen.ledger import FinalLedger

MAX_PAIR_LAG_S = 60


def check_ledger(ctx: GenContext, ledger: FinalLedger) -> list[str]:
    """Balances never negative, double entry consistent, no dates after as_of."""
    problems: list[str] = []
    cols = ledger.cols
    if (ledger.balance_after < 0).any():
        bad = sorted({str(a) for a in cols["account"][ledger.balance_after < 0]})
        problems.append(f"negative balances on {len(bad)} accounts: {bad[:5]}")
    if (cols["ts"] >= ctx.tb.end_ts).any():
        problems.append(f"{int((cols['ts'] >= ctx.tb.end_ts).sum())} entries after as_of")
    # Recompute balance sequence per account.
    acct = cols["account"]
    starts = np.r_[0, np.flatnonzero(acct[1:] != acct[:-1]) + 1]
    signed = cols["sign"] * cols["paise"]
    expected_first = np.array([ledger.opening[a] for a in acct[starts]]) + signed[starts]
    if not np.array_equal(ledger.balance_after[starts], expected_first):
        problems.append("first balance_after does not match opening + amount")
    diffs = np.diff(ledger.balance_after)
    same = acct[1:] == acct[:-1]
    if not np.array_equal(diffs[same], signed[1:][same]):
        problems.append("balance_after sequence breaks inside an account")
    # Double entry: groups with two rows must mirror each other.
    groups = Counter(int(g) for g in cols["group"])
    pairs = {g for g, n in groups.items() if n == 2}
    by_group: dict[int, list[int]] = {}
    for i, g in enumerate(cols["group"]):
        if int(g) in pairs:
            by_group.setdefault(int(g), []).append(i)
    broken = 0
    for i, j in by_group.values():
        if cols["paise"][i] != cols["paise"][j] or cols["sign"][i] != -cols["sign"][j] or abs(int(cols["ts"][i]) - int(cols["ts"][j])) > MAX_PAIR_LAG_S:
            broken += 1
    if broken:
        problems.append(f"{broken} double-entry pairs disagree")
    if any(n > 2 for n in groups.values()):
        problems.append("a transfer group has more than two sides")
    return problems


def check_coverage(ctx: GenContext, alerted: set[str], max_organic: int) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Return (planted accounts without an alert, organic alert count, warnings)."""
    planted = {t["account_id"] for t in ctx.truth}
    missing = [t for t in ctx.truth if t["account_id"] not in alerted]
    organic = len(alerted - planted)
    warnings = []
    if organic > max_organic:
        warnings.append(f"organic alerts {organic} exceed the target of {max_organic}")
    return missing, organic, warnings

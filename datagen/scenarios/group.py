"""Group collections: a society festival fund and a chit / rent-split group.

Many small, round payments from the same members who have paid for months,
followed by one large payout to a vendor or a member. Expected disposition is
Close.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from datagen.context import Account
from datagen.scenarios.base import Scenario, register_scenario
from datagen.timebase import DAY_S, HOUR_S

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@register_scenario
class GroupCollectionScenario(Scenario):
    """Society funds and chit or rent-split groups."""

    name = "group"

    def build(self, variant: str, ordinal: int) -> Account:
        p = self.vp(variant)
        acct = self._society(p) if variant == "society_fund" else self._chit(p)
        self.ctx.add_truth(acct.id, f"group.{variant}", "legitimate", "close", list(p["planted_signals"]))
        return acct

    def _society(self, p: dict[str, Any]) -> Account:
        ctx, tb, rng = self.ctx, self.ctx.tb, self.rng
        acct = self.account("treasurer", opened_days_before_window=p["opened_days_before_window"])
        members = ctx.pick("individual", self.rint(p["members"]))
        acct.favourites["members"] = members
        acct.declared_turnover = len(members) * 2_500
        self.backstory(acct, "treasurer")
        start = tb.window_start_ts + self.rint([0, 1]) * DAY_S
        collect_end = tb.end_ts - 4 * DAY_S
        total = 0
        festival = str(rng.choice(p["festivals"]))
        for m in members:
            if rng.random() > p["pay_share"]:
                continue
            ts = int(self.times(1, start, collect_end, hours="evening")[0])
            amount = int(rng.choice(p["amounts"])) * 100
            self.receive(acct, ts, amount, m, "upi", f"UPI/{self.ref()}/{ctx.cp_name(m)}/{festival} contribution")
            total += amount
        vendors = ctx.pick("vendor", 2)
        pay_ts = collect_end + 2 * DAY_S + 11 * HOUR_S
        split = (0.6, 0.25)
        for v, s in zip(vendors, split, strict=True):
            self.pay(acct, pay_ts, int(total * s) // 100 * 100, v, "neft", f"NEFT/{self.ref()}/{ctx.cp_name(v)}/{festival} arrangements")
        return acct

    def _chit(self, p: dict[str, Any]) -> Account:
        ctx, tb, rng = self.ctx, self.ctx.tb, self.rng
        members = ctx.pick("individual", self.rint(p["members"]))
        installment = self.rint(p["installment"]) // 1000 * 1000
        pot = installment * len(members)
        acct = self.account("salaried", opened_days_before_window=p["opened_days_before_window"], occupation=str(rng.choice(p["occupations"])), declared_turnover=int(pot * 1.1))
        self.backstory(acct, "salaried")
        winners = list(rng.permutation(len(members)))
        for k, month in enumerate(tb.month_starts()):
            cycle = month + (p["collect_day"] - 1) * DAY_S
            if cycle < tb.dataset_start_ts or cycle + 5 * DAY_S >= tb.end_ts:
                continue
            mon = MONTHS[int(np.datetime64(cycle, "s").astype(object).month) - 1]
            for m in members:
                ts = cycle + self.rint([0, 2]) * DAY_S + self.rint([8, 21]) * HOUR_S + self.rint([0, 3599])
                self.receive(acct, ts, installment * 100, m, str(rng.choice(["upi", "imps"])), f"UPI/{self.ref()}/{ctx.cp_name(m)}/chit installment {mon}")
            winner = members[int(winners[k % len(members)])]
            payout = int(pot * (1 - p["commission"])) * 100
            self.pay(acct, cycle + 3 * DAY_S + 11 * HOUR_S, payout, winner, "neft", f"NEFT/{self.ref()}/{ctx.cp_name(winner)}/chit prize {mon}")
        return acct

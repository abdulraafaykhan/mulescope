"""Dormant accounts that wake up in the alert window.

Variants: mule_like (12+ months silent, stale KYC, sudden fan-in from
unrelated senders swept out within hours; expected Escalate) and legit (one
large maturity or property-sale credit, a few outflows days later; expected
Close).
"""

from __future__ import annotations

from typing import Any

from datagen.context import Account
from datagen.ledger import CREDIT
from datagen.scenarios.base import Scenario, register_scenario
from datagen.scenarios.mule import VICTIM_REMARKS
from datagen.timebase import DAY_S, HOUR_S


@register_scenario
class DormantScenario(Scenario):
    """Long-silent accounts with sudden activity."""

    name = "dormant"

    def build(self, variant: str, ordinal: int) -> Account:
        p = self.vp(variant)
        ctx, tb, rng = self.ctx, self.ctx.tb, self.rng
        acct = self.account("dormant", opened_days_before_window=p["opened_days_before_window"], occupation=str(rng.choice(p["occupations"])), declared_turnover=self.rint(p["declared_turnover"]))
        cust = ctx.customers[acct.customer_id]
        cust.kyc_status = p["kyc_status"]
        cust.kyc_refreshed_ts = tb.window_start_ts - self.rint(p["kyc_age_days"]) * DAY_S
        last = tb.window_start_ts - self.rint(p["silent_days"]) * DAY_S
        bank = ctx.pick("bank")
        ctx.ledger.add(acct.id, last, CREDIT, self.rint([300, 3000]) * 100, "neft", "counterparty", bank, ctx.cp_name(bank), "Savings interest credit")
        if variant == "mule_like":
            self._mule_like(acct, p)
        else:
            self._legit(acct, p)
        label, expected = ("suspicious", "escalate") if variant == "mule_like" else ("legitimate", "close")
        ctx.add_truth(acct.id, f"dormant.{variant}", label, expected, list(p["planted_signals"]))
        return acct

    def _mule_like(self, acct: Account, p: dict[str, Any]) -> None:
        tb = self.ctx.tb
        senders = self.ctx.pick("individual", self.rint(p["senders"]))

        def remark(s: str) -> str:
            return VICTIM_REMARKS[int(self.rng.integers(len(VICTIM_REMARKS)))].format(ref=self.ref(), name=self.ctx.cp_name(s))

        start = tb.window_start_ts + self.rint([1, 3]) * DAY_S
        credits = self.fan_in(acct, senders, int(len(senders) * 1.2), start, tb.end_ts, p["median_credit"], 0.5, remark, round_to=500, p_round=0.5, hours="daytime")
        bens = [self.ctx.new_individual(pool=None) for _ in range(2)]
        self.sweep(
            acct, credits, delay_min=p["exit_minutes"], fraction=[0.92, 0.98], keep_paise=self.rint([300, 900]) * 100,
            beneficiaries=[("cp", bens[0]), ("cp", bens[1])], weights=[0.75, 0.25], chunk_paise={"cp": 15_000_000},
            remark=lambda k, r: f"IMPS/P2A/{self.ref()}/{self.ctx.cp_name(r or '')}",
            sweep_existing=True,
        )

    def _legit(self, acct: Account, p: dict[str, Any]) -> None:
        ctx, tb, rng = self.ctx, self.ctx.tb, self.rng
        amount = self.rint(p["large_credit"]) // 1000 * 1000 * 100
        ts = tb.window_start_ts + self.rint([1, 4]) * DAY_S + 11 * HOUR_S
        if rng.random() < 0.5:
            src = ctx.pick("bank")
            self.receive(acct, ts, amount + self.rint([1, 99]) * 100 + self.rint([1, 99]), src, "neft", f"FD maturity proceeds {ctx.cp_name(src)}")
        else:
            src = ctx.pick("individual")
            self.receive(acct, ts, amount, src, "rtgs", f"RTGS/{self.ref()}/{ctx.cp_name(src)}/sale consideration flat")
        parties = [ctx.new_individual(pool=None) for _ in range(4)]
        purposes = ("home loan prepayment", "transfer to son", "daughter education fees", "medical expenses")
        for k, (share, who) in enumerate(zip(p["outflow_shares"], parties, strict=True)):
            out_ts = ts + (2 + 2 * k) * DAY_S + self.rint([1, 6]) * HOUR_S
            if out_ts >= tb.end_ts:
                continue
            channel = "rtgs" if amount * share > 20_000_000 else "neft"
            self.pay(acct, out_ts, int(amount * share) // 100 * 100, who, channel, f"{channel.upper()}/{self.ref()}/{ctx.cp_name(who)}/{purposes[k]}")

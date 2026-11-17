"""Ambiguous and adversarial cases that need a human or test the policy.

Variants: new_business (looks like a seller but has no history and no GST
evidence; Escalate), partial_signals (fan-in from unrelated senders but slower
exits and retained balances; Escalate), complaint_coincidence (a clean,
established shop where a single sender has a fraud complaint; Close).
"""

from __future__ import annotations

from typing import Any

from datagen.context import Account
from datagen.scenarios.base import Scenario, register_scenario
from datagen.scenarios.mule import VICTIM_REMARKS
from datagen.scenarios.seller import build_shop, daily_sales
from datagen.timebase import DAY_S


@register_scenario
class AmbiguousScenario(Scenario):
    """Cases where the evidence is mixed."""

    name = "ambiguous"

    def build(self, variant: str, ordinal: int) -> Account:
        p = self.vp(variant)
        if variant == "new_business":
            acct, label, expected = self._new_business(p), "ambiguous", "escalate"
        elif variant == "partial_signals":
            acct, label, expected = self._partial(p), "ambiguous", "escalate"
        else:
            acct, label, expected = self._coincidence(p), "legitimate", "close"
        self.ctx.add_truth(acct.id, f"ambiguous.{variant}", label, expected, list(p["planted_signals"]))
        return acct

    def _new_business(self, p: dict[str, Any]) -> Account:
        ctx, tb = self.ctx, self.ctx.tb
        acct = self.account("small_business", opened_days_before_window=p["opened_days_before_window"], occupation=str(self.rng.choice(p["occupations"])), declared_turnover=self.rint(p["declared_turnover"]))
        early = daily_sales(self, acct, start=acct.opened_ts + DAY_S, end=tb.window_start_ts, per_day=p["early_sales_per_day"], median=p["median_sale"], sigma=0.6, loyal=ctx.pick("individual", 10), loyal_share=0.3)
        window = daily_sales(self, acct, start=tb.window_start_ts, end=tb.end_ts, per_day=self.runif(p["sales_per_day"]), median=p["median_sale"], sigma=0.6, loyal=ctx.pick("individual", 5), loyal_share=0.05)
        suppliers = [ctx.new_individual(pool=None) for _ in range(2)]
        from datagen.scenarios.base import Credit

        credits = [Credit(ts, paise, s, g) for ts, paise, s, g in early + window]
        self.sweep(
            acct, credits, delay_min=p["exit_minutes"], fraction=p["sweep_fraction"], keep_paise=200_000,
            beneficiaries=[("cp", suppliers[0]), ("cp", suppliers[1])], weights=[0.6, 0.4], chunk_paise={"cp": 15_000_000},
            remark=lambda k, r: f"IMPS/{self.ref()}/{ctx.cp_name(r or '')}/stock purchase",
        )
        return acct

    def _partial(self, p: dict[str, Any]) -> Account:
        ctx, tb = self.ctx, self.ctx.tb
        acct = self.account("salaried", opened_days_before_window=p["opened_days_before_window"], declared_turnover=self.rint(p["declared_turnover"]))
        self.backstory(acct, "salaried")
        senders = ctx.pick("individual", self.rint(p["senders"]))

        def remark(s: str) -> str:
            return VICTIM_REMARKS[int(self.rng.integers(len(VICTIM_REMARKS)))].format(ref=self.ref(), name=ctx.cp_name(s))

        credits = self.fan_in(acct, senders, int(len(senders) * 1.15), tb.window_start_ts, tb.end_ts - 2 * DAY_S, p["median_credit"], 0.5, remark, round_to=500, p_round=0.4)
        bens = [ctx.new_individual(pool=None) for _ in range(2)]
        self.sweep(
            acct, credits, delay_min=p["exit_minutes"], fraction=p["sweep_fraction"], keep_paise=self.rint([20_000, 60_000]) * 100,
            beneficiaries=[("cp", bens[0]), ("cp", bens[1])], weights=[0.8, 0.2], chunk_paise={"cp": 15_000_000},
            remark=lambda k, r: f"IMPS/{self.ref()}/{ctx.cp_name(r or '')}",
        )
        return acct

    def _coincidence(self, p: dict[str, Any]) -> Account:
        acct, sales = build_shop(self, p)
        tb = self.ctx.tb
        in_window = [s for s in sales if s[0] >= tb.window_start_ts]
        ts, paise, sender, group = in_window[int(self.rng.integers(len(in_window)))]
        self.ctx.complaints.append({"victim": sender, "beneficiary": acct.id, "groups": [group], "reported_ts": min(ts + 2 * DAY_S, tb.end_ts - 3600), "paise": paise})
        return acct

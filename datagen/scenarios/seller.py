"""Legitimate sellers and freelancers that a crude detector still flags.

Variants: shop (GST-style business with repeat customers and weekly supplier
payouts), online_with_refunds (many new buyers, refunds to the same buyers),
freelancer (few clients, invoice-sized round amounts, vendors paid days
later). All have 90+ days of the same pattern before the window. Expected
disposition is Close.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from datagen.context import Account
from datagen.scenarios.base import Scenario, register_scenario
from datagen.timebase import DAY_S, HOUR_S


def daily_sales(scn: Scenario, acct: Account, *, start: int, end: int, per_day: float, median: float, sigma: float, loyal: list[str], loyal_share: float) -> list[tuple[int, int, str, int]]:
    """Plant customer payments; returns ``(ts, paise, sender, group)`` rows."""
    rng, ctx = scn.rng, scn.ctx
    n_days = (end - start) // DAY_S
    out: list[tuple[int, int, str, int]] = []
    for d in range(n_days):
        day0 = start + d * DAY_S
        n = int(rng.poisson(per_day * (1.3 if ((day0 // DAY_S + 3) % 7) >= 5 else 1.0)))
        if n == 0:
            continue
        ts = np.sort(scn.times(n, day0, day0 + DAY_S, hours="daytime"))
        amounts = scn.amounts(n, median, sigma) + rng.integers(0, 100, size=n)
        for t, p in zip(ts, amounts, strict=True):
            sender = loyal[int(rng.integers(len(loyal)))] if rng.random() < loyal_share else ctx.pick("individual")
            g = scn.receive(acct, int(t), int(p), sender, "upi", f"UPI/P2M/{scn.ref()}/{ctx.cp_name(sender)}")
            out.append((int(t), int(p), sender, g))
    return out


def supplier_payouts(scn: Scenario, acct: Account, sales: list[tuple[int, int, str, int]], *, start: int, end: int, every_days: int, share: tuple[float, float], suppliers: list[str]) -> None:
    """Pay suppliers a share of the inflow of each period, by NEFT/IMPS."""
    rng = scn.rng
    t = start + every_days * DAY_S
    while t < end:
        period = sum(p for ts, p, _, _ in sales if t - every_days * DAY_S <= ts < t)
        amount = int(period * scn.runif(share))
        k = int(rng.integers(2, min(4, len(suppliers)) + 1))
        picks = [suppliers[int(i)] for i in rng.choice(len(suppliers), size=k, replace=False)]
        split = rng.dirichlet(np.ones(k)) * amount
        for s, a in zip(picks, split, strict=True):
            if a < 100_000:
                continue
            ts = t + int(rng.integers(10, 17)) * HOUR_S
            scn.pay(acct, ts, int(a) // 100 * 100, s, str(rng.choice(["neft", "imps"])), f"NEFT/{scn.ref()}/{scn.ctx.cp_name(s)}/inv {int(rng.integers(1000, 9999))}")
        t += every_days * DAY_S


def build_shop(scn: Scenario, p: dict[str, Any]) -> tuple[Account, list[tuple[int, int, str, int]]]:
    """A GST-registered shop with a long, steady history. Shared with ambiguous."""
    ctx, tb = scn.ctx, scn.ctx.tb
    per_day, median = scn.runif(p["sales_per_day"]), float(p["median_sale"])
    monthly = int(per_day * 30 * median * 1.15)
    acct = scn.account("small_business", opened_days_before_window=p["opened_days_before_window"], occupation=str(scn.rng.choice(p["occupations"])), declared_turnover=int(round(monthly * scn.runif([0.9, 1.2]), -3)))
    acct.type = "current"
    loyal = ctx.pick("individual", scn.rint(p["loyal_customers"]))
    start = tb.window_start_ts - p["history_days"] * DAY_S
    sales = daily_sales(scn, acct, start=start, end=tb.end_ts, per_day=per_day, median=median, sigma=0.7, loyal=loyal, loyal_share=p["loyal_share"])
    suppliers = ctx.pick("supplier", 5)
    supplier_payouts(scn, acct, sales, start=start, end=tb.end_ts, every_days=7, share=tuple(p["supplier_share"]), suppliers=suppliers)
    gst = ctx.pick("gov")
    for month in tb.month_starts():
        ts = month + 19 * DAY_S + 11 * HOUR_S
        if start <= ts < tb.end_ts:
            month_sales = sum(s[1] for s in sales if month <= s[0] < month + 30 * DAY_S)
            scn.pay(acct, ts, int(month_sales * 0.03) // 100 * 100 + 10_000, gst, "neft", f"GST payment CPIN {scn.ref()}")
    return acct, sales


@register_scenario
class SellerScenario(Scenario):
    """Shops, online sellers and freelancers."""

    name = "seller"

    def build(self, variant: str, ordinal: int) -> Account:
        p = self.vp(variant)
        if variant == "shop":
            acct, _ = build_shop(self, p)
        elif variant == "online_with_refunds":
            acct = self._online(p)
        else:
            acct = self._freelancer(p)
        self.ctx.add_truth(acct.id, f"seller.{variant}", "legitimate", "close", list(p["planted_signals"]))
        return acct

    def _online(self, p: dict[str, Any]) -> Account:
        ctx, tb, rng = self.ctx, self.ctx.tb, self.rng
        per_day, median = self.runif(p["sales_per_day"]), float(p["median_sale"])
        acct = self.account("small_business", opened_days_before_window=p["opened_days_before_window"], occupation="Online seller (marketplace)", declared_turnover=int(round(per_day * 30 * median * 1.1, -3)))
        acct.type = "current"
        loyal = ctx.pick("individual", 60)
        start = tb.window_start_ts - p["history_days"] * DAY_S
        sales = daily_sales(self, acct, start=start, end=tb.end_ts, per_day=per_day, median=median, sigma=0.6, loyal=loyal, loyal_share=0.2)
        for ts, paise, sender, _ in sales:
            if rng.random() < p["refund_share"]:
                when = ts + self.rint([1, 3]) * DAY_S + self.rint([1, 6]) * HOUR_S
                if when < tb.end_ts:
                    self.pay(acct, when, paise, sender, "upi", f"UPI/{self.ref()}/Refund order {int(rng.integers(10**7, 10**8))}")
        supplier_payouts(self, acct, sales, start=start, end=tb.end_ts, every_days=5, share=tuple(p["supplier_share"]), suppliers=ctx.pick("supplier", 4))
        return acct

    def _freelancer(self, p: dict[str, Any]) -> Account:
        ctx, tb, rng = self.ctx, self.ctx.tb, self.rng
        acct = self.account("freelancer", opened_days_before_window=p["opened_days_before_window"])
        clients = ctx.pick("client", self.rint(p["clients"]))
        acct.favourites["client"] = clients
        self.backstory(acct, "freelancer")
        vendors = [ctx.new_individual(pool=None) for _ in range(2)]
        start = tb.window_start_ts - p["history_days"] * DAY_S
        invoices: list[tuple[int, int]] = []
        t = start
        while t < tb.window_start_ts:
            invoices.append((t + self.rint([0, 6]) * DAY_S, 0))
            t += self.rint(p["history_gap_days"]) * DAY_S
        window_ts = self.times(self.rint(p["window_invoices"]), tb.window_start_ts, tb.end_ts - 3 * DAY_S, hours="bank")
        invoices += [(int(x), 0) for x in window_ts]
        total_window = 0
        for ts, _ in invoices:
            amount = int(rng.choice(p["invoice_amounts"])) * 100
            client = clients[int(rng.integers(len(clients)))]
            self.receive(acct, ts, amount, client, str(rng.choice(["neft", "imps"])), f"NEFT/{self.ref()}/{ctx.cp_name(client)}/INV-{int(rng.integers(100, 999))}")
            pay_ts = ts + self.rint([2, 4]) * DAY_S
            if pay_ts < tb.end_ts:
                share = int(amount * self.runif(p["vendor_share"])) // 100 * 100
                v = vendors[int(rng.integers(2))]
                self.pay(acct, pay_ts, share, v, "imps", f"IMPS/{self.ref()}/{ctx.cp_name(v)}/subcontract")
            if ts >= tb.window_start_ts:
                total_window += amount
        return acct

"""Vectorised transaction engine and the background (normal-world) population.

``PersonaEngine.generate`` turns a persona's templates into ledger rows for a
set of accounts with NumPy (no per-row loops for amounts, times or channels;
only remark strings are formatted per row). ``build_population`` creates the
background customers and accounts by persona share, plus a few organic noise
accounts that look slightly odd but are fine.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from datagen.context import Account, GenContext
from datagen.factories.personas import HOUR_CURVES, PERSONAS, Persona, Template
from datagen.ledger import CREDIT, DEBIT
from datagen.timebase import DAY_S, HOUR_S, IST_OFFSET_S, ist_midnight_utc, to_datetime

UPI_LIMIT_RUPEES = 100_000
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _hour_probs(key: str) -> np.ndarray:
    w = np.asarray(HOUR_CURVES[key], dtype=float)
    return w / w.sum()


def _align_day(ts: np.ndarray) -> np.ndarray:
    return ts - ((ts + IST_OFFSET_S) % DAY_S)


def account_city(ctx: GenContext, acct: Account) -> str:
    return ctx.customers[acct.customer_id].city


class PersonaEngine:
    """Generates ledger rows from persona templates."""

    def __init__(self, ctx: GenContext) -> None:
        self.ctx = ctx
        fest = ctx.params["population"]["festival"]
        self.fest_start = ist_midnight_utc(date.fromisoformat(fest["start"]))
        self.fest_end = ist_midnight_utc(date.fromisoformat(fest["end"]))
        self.months = np.asarray(ctx.tb.month_starts(), dtype=np.int64)

    # --- favourites -----------------------------------------------------------

    def _favourites(self, accts: list[Account], key: str, pool: str, k: int) -> np.ndarray:
        rng = self.ctx.rng
        out = np.empty((len(accts), max(k, 1)), dtype=object)
        for i, acct in enumerate(accts):
            if key not in acct.favourites:
                acct.favourites[key] = self.ctx.pick(pool, max(k, 1))
            fav = acct.favourites[key]
            out[i, :] = [fav[j % len(fav)] for j in range(max(k, 1))]
        del rng
        return out

    # --- timing ---------------------------------------------------------------

    def _poisson_times(self, tpl: Template, start: np.ndarray, end: np.ndarray, include: np.ndarray, hours: str) -> tuple[np.ndarray, np.ndarray]:
        rng = self.ctx.rng
        span_days = np.maximum((end - start) / DAY_S, 0)
        boost = max(tpl.weekend_boost, 1.0) * max(tpl.festival_mult, 1.0)
        lam = tpl.rate * span_days / 30.0 * include * boost
        counts = rng.poisson(lam)
        idx = np.repeat(np.arange(len(start)), counts)
        if len(idx) == 0:
            return idx, np.empty(0, dtype=np.int64)
        day0 = _align_day(start)[idx]
        days = np.floor(rng.random(len(idx)) * np.ceil(span_days[idx] + 1)).astype(np.int64)
        day_ts = day0 + days * DAY_S
        weekday = ((day_ts + IST_OFFSET_S) // DAY_S + 3) % 7
        weight = np.where(weekday >= 5, max(tpl.weekend_boost, 1.0), 1.0)
        weight = weight * np.where((day_ts >= self.fest_start) & (day_ts < self.fest_end), max(tpl.festival_mult, 1.0), 1.0)
        keep = rng.random(len(idx)) < weight / boost
        hour = rng.choice(24, size=len(idx), p=_hour_probs(hours))
        ts = day_ts + hour * HOUR_S + rng.integers(0, HOUR_S, size=len(idx))
        keep &= (ts >= start[idx]) & (ts < end[idx])
        return idx[keep], ts[keep]

    def _monthly_times(self, tpl: Template, start: np.ndarray, end: np.ndarray, include: np.ndarray, hours: str) -> tuple[np.ndarray, np.ndarray]:
        rng = self.ctx.rng
        n, m = len(start), len(self.months)
        lo, hi = tpl.day
        day = rng.integers(lo, hi + 1, size=(n, m))
        hour = rng.choice(24, size=(n, m), p=_hour_probs(hours))
        ts = self.months[None, :] + (day - 1) * DAY_S + hour * HOUR_S + rng.integers(0, HOUR_S, size=(n, m))
        ok = (rng.random((n, m)) < tpl.rate) & include[:, None].astype(bool)
        ok &= (ts >= start[:, None]) & (ts < end[:, None])
        idx = np.repeat(np.arange(n), m).reshape(n, m)
        return idx[ok], ts[ok]

    # --- amounts --------------------------------------------------------------

    def _amounts(self, tpl: Template, base: np.ndarray) -> np.ndarray:
        rng = self.ctx.rng
        rupees = base * rng.lognormal(0.0, tpl.sigma, size=len(base)) if tpl.sigma > 0 else base.astype(float)
        rupees = np.maximum(rupees, 10.0)
        if tpl.round_to:
            rounded = np.maximum(np.round(rupees / tpl.round_to) * tpl.round_to, tpl.round_to)
            rupees = np.where(rng.random(len(base)) < tpl.p_round, rounded, np.round(rupees))
        else:
            rupees = np.round(rupees)
        paise = rupees.astype(np.int64) * 100
        if tpl.paise:
            not_round = (rupees % 10) != 0
            paise = paise + np.where(not_round, rng.integers(0, 100, size=len(base)), 0)
        return paise

    # --- main -----------------------------------------------------------------

    def generate(
        self,
        persona: Persona,
        accts: list[Account],
        start: np.ndarray,
        end: np.ndarray,
        scale: np.ndarray,
        monthly_income: np.ndarray,
        allow_internal: bool = True,
    ) -> int:
        """Append rows for ``accts`` over ``[start, end)``; returns rows added."""
        if not accts:
            return 0
        ctx, rng = self.ctx, self.ctx.rng
        start = np.asarray(start, dtype=np.int64)
        end = np.asarray(end, dtype=np.int64)
        cities = np.asarray([account_city(ctx, a) for a in accts], dtype=object)
        added = 0
        for tpl in persona.templates:
            include = (rng.random(len(accts)) < tpl.include_prob).astype(float)
            hours = tpl.hours or persona.hours
            if tpl.kind == "members":
                added += self._members(persona, tpl, accts, start, end, hours)
                continue
            times = self._monthly_times if tpl.kind == "monthly" else self._poisson_times
            idx, ts = times(tpl, start, end, include, hours)
            if len(idx) == 0:
                continue
            base = monthly_income[idx] * rng.uniform(0.92, 1.0, size=len(idx)) if tpl.median == 0 else tpl.median * scale[idx]
            paise = self._amounts(tpl, np.asarray(base, dtype=float))
            chans, probs = zip(*tpl.channels, strict=True)
            channel = rng.choice(np.asarray(chans, dtype=object), size=len(idx), p=np.asarray(probs) / sum(probs))
            channel = np.where((channel == "upi") & (paise > UPI_LIMIT_RUPEES * 100), "neft", channel)
            added += self._emit(tpl, accts, idx, ts, paise, channel, cities, allow_internal)
        return added

    def _emit(self, tpl: Template, accts: list[Account], idx: np.ndarray, ts: np.ndarray, paise: np.ndarray, channel: np.ndarray, cities: np.ndarray, allow_internal: bool) -> int:
        ctx, rng = self.ctx, self.ctx.rng
        n = len(idx)
        account = np.asarray([accts[i].id for i in idx], dtype=object)
        cp_type = np.full(n, "counterparty", dtype=object)
        cp_ref = np.empty(n, dtype=object)
        internal = np.zeros(n, dtype=bool)
        kind = tpl.cp[0]
        if kind == "atm":
            cp_type[:] = "atm"
            cp_ref[:] = None
        elif kind == "pool":
            pool = ctx.pools[tpl.cp[1]]
            cp_ref[:] = [pool[int(j)] for j in rng.integers(0, len(pool), size=n)]
        elif kind == "fav":
            _, key, pool, k = tpl.cp
            fav = self._favourites(accts, key, pool, k)
            cp_ref[:] = fav[idx, rng.integers(0, fav.shape[1], size=n)]
        elif kind == "p2p":
            internal_p = tpl.cp[1] if allow_internal and len(ctx.background_accounts) > 1 else 0.0
            internal = rng.random(n) < internal_p
            fav = self._favourites(accts, "friends", "individual", 6)
            cp_ref[:] = fav[idx, rng.integers(0, 6, size=n)]
            partners = rng.integers(0, len(ctx.background_accounts), size=n)
            for j in np.flatnonzero(internal):
                partner = ctx.background_accounts[int(partners[j])]
                if partner == account[j]:
                    internal[j] = False
                    continue
                cp_type[j] = "account"
                cp_ref[j] = partner
        names = np.asarray(
            [
                (f"ATM {cities[i]}" if t == "atm" else (ctx.accounts[r].holder_name if t == "account" else ctx.cp_name(r)))
                for i, t, r in zip(idx, cp_type, cp_ref, strict=True)
            ],
            dtype=object,
        )
        months = [MONTHS[to_datetime(int(t) + IST_OFFSET_S).month - 1] for t in ts]
        tidx = rng.integers(0, len(tpl.remarks), size=n)
        refs = rng.integers(10**11, 10**12 - 1, size=n)
        remarks = np.asarray(
            [
                tpl.remarks[int(tidx[j])].format(month=months[j], cp=names[j], ref=int(refs[j]), city=cities[idx[j]], first=accts[idx[j]].first_name)[:140]
                for j in range(n)
            ],
            dtype=object,
        )
        groups = ctx.ledger.new_groups(n)
        sign = np.full(n, tpl.sign, dtype=np.int64)
        ctx.ledger.add_batch(account=account, ts=ts, sign=sign, paise=paise, channel=channel, cp_type=cp_type, cp_ref=cp_ref, cp_name=names, remarks=remarks, group=groups)
        if internal.any():
            j = np.flatnonzero(internal)
            mirror_names = np.asarray([accts[i].holder_name for i in idx[j]], dtype=object)
            ctx.ledger.add_batch(
                account=cp_ref[j], ts=ts[j] + rng.integers(2, 30, size=len(j)), sign=-sign[j], paise=paise[j], channel=channel[j],
                cp_type=np.full(len(j), "account", dtype=object), cp_ref=account[j], cp_name=mirror_names,
                remarks=np.asarray([f"UPI/P2P/{int(refs[k])}/{mirror_names[x]}" for x, k in enumerate(j)], dtype=object), group=groups[j],
            )
        return n + int(internal.sum())

    def _members(self, persona: Persona, tpl: Template, accts: list[Account], start: np.ndarray, end: np.ndarray, hours: str) -> int:
        ctx, rng = self.ctx, self.ctx.rng
        lo_n, hi_n = persona.extra["members"]
        lo_a, hi_a = persona.extra["member_amount"]
        rows = 0
        for i, acct in enumerate(accts):
            if "members" not in acct.favourites:
                acct.favourites["members"] = ctx.pick("individual", int(rng.integers(lo_n, hi_n + 1)))
            members = acct.favourites["members"]
            dues = (np.round(rng.uniform(lo_a, hi_a, size=len(members)) / 500) * 500).astype(np.int64)
            for month in self.months:
                pay = rng.random(len(members)) < tpl.rate
                day = rng.integers(tpl.day[0], tpl.day[1] + 1, size=len(members))
                hour = rng.choice(24, size=len(members), p=_hour_probs(hours))
                ts = month + (day - 1) * DAY_S + hour * HOUR_S + rng.integers(0, HOUR_S, size=len(members))
                for m in np.flatnonzero(pay & (ts >= start[i]) & (ts < end[i])):
                    mon = MONTHS[to_datetime(int(ts[m]) + IST_OFFSET_S).month - 1]
                    cp = members[int(m)]
                    remark = tpl.remarks[int(rng.integers(len(tpl.remarks)))].format(month=mon, cp=ctx.cp_name(cp), ref=ctx.names.upi_ref())
                    ctx.ledger.add(acct.id, int(ts[m]), CREDIT, int(dues[m]) * 100, "upi", "counterparty", cp, ctx.cp_name(cp), remark)
                    rows += 1
        return rows


# --- population ---------------------------------------------------------------


def _persona_counts(ctx: GenContext, n_customers: int) -> dict[str, int]:
    shares: dict[str, float] = ctx.params["population"]["persona_shares"]
    raw = {k: v * n_customers for k, v in shares.items()}
    counts = {k: int(np.floor(v)) for k, v in raw.items()}
    remainder = n_customers - sum(counts.values())
    for k in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)[:remainder]:
        counts[k] += 1
    return counts


def create_persona_account(ctx: GenContext, persona: Persona, *, opened_ts: int | None = None, occupation: str | None = None) -> Account:
    """Create one customer + primary account for ``persona``."""
    rng = ctx.rng
    income = int(rng.integers(persona.income[0], persona.income[1] + 1)) if persona.income[1] else 0
    income = int(round(income, -3))
    cust, first, last = ctx.new_customer(occupation or str(rng.choice(persona.occupations)), income, age_range=persona.age)
    turnover = max(int(income / 12 * persona.turnover_factor), 3000)
    if opened_ts is None:
        opened_ts = ctx.tb.dataset_start_ts - int(rng.integers(200, 3000)) * DAY_S
    opening = int(max(income / 12 * persona.opening_months, 500) * 100 * rng.uniform(0.6, 1.4))
    holder = None
    if persona.name == "treasurer":
        holder = f"{last} {str(rng.choice(['Residency CHS', 'Heights Society', 'Temple Trust', 'Nagar RWA']))}"
    return ctx.new_account(cust, first, last, persona=persona.name, opened_ts=opened_ts, declared_turnover=int(round(turnover, -2)), acct_type=persona.acct_type, holder_name=holder, base_opening_paise=opening)


def _monthly_income(ctx: GenContext, acct: Account) -> float:
    return ctx.customers[acct.customer_id].declared_income / 12.0


def build_population(ctx: GenContext, n_customers: int) -> list[Account]:
    """Create the background population and generate its 180-day ledger."""
    rng = ctx.rng
    by_persona: dict[str, list[Account]] = {}
    for name, count in _persona_counts(ctx, n_customers).items():
        persona = PERSONAS[name]
        for _ in range(count):
            acct = create_persona_account(ctx, persona)
            by_persona.setdefault(name, []).append(acct)
            if rng.random() < persona.second_account_p:
                cust = ctx.customers[acct.customer_id]
                second = ctx.new_account(cust, acct.first_name, cust.name.split()[-1], persona=name, opened_ts=acct.opened_ts + int(rng.integers(30, 400)) * DAY_S, declared_turnover=acct.declared_turnover, acct_type="savings", with_vpa=False, base_opening_paise=200_000)
                by_persona[name].append(second)
    ctx.background_accounts = [a.id for accts in by_persona.values() for a in accts]

    engine = PersonaEngine(ctx)
    for name, accts in by_persona.items():
        persona = PERSONAS[name]
        start = np.asarray([max(a.opened_ts, ctx.tb.dataset_start_ts) for a in accts], dtype=np.int64)
        end = np.full(len(accts), ctx.tb.end_ts, dtype=np.int64)
        scale = rng.lognormal(0.0, 0.3, size=len(accts))
        income = np.asarray([_monthly_income(ctx, a) for a in accts], dtype=float)
        engine.generate(persona, accts, start, end, scale, income)
    _organic_noise(ctx, by_persona.get("salaried", []))
    _dormant_last_activity(ctx, by_persona.get("dormant", []))
    return [a for accts in by_persona.values() for a in accts]


def _organic_noise(ctx: GenContext, salaried: list[Account]) -> None:
    """A few fine accounts that look slightly odd: trip and wedding gift splits."""
    rng = ctx.rng
    cfg: dict[str, Any] = ctx.params["population"]["organic_noise"]
    for acct in salaried[: cfg["accounts"]]:
        day0 = ctx.tb.dataset_start_ts + int(rng.integers(10, 170)) * DAY_S
        friends = ctx.pick("individual", int(rng.integers(cfg["friends"][0], cfg["friends"][1] + 1)))
        share = int(rng.integers(cfg["share"][0], cfg["share"][1])) // 100 * 100
        total = 0
        for f in friends:
            ts = day0 + int(rng.integers(0, 3 * DAY_S))
            ctx.ledger.add(acct.id, ts, CREDIT, share * 100, "upi", "counterparty", f, ctx.cp_name(f), f"UPI/{ctx.names.upi_ref()}/{ctx.cp_name(f)}/Goa trip share")
            total += share
        agent = ctx.pick("travel")
        ctx.ledger.add(acct.id, day0 + 4 * DAY_S, DEBIT, int(total * 0.95) * 100, "neft", "counterparty", agent, ctx.cp_name(agent), f"NEFT/{ctx.names.upi_ref()}/{ctx.cp_name(agent)}/group booking")


def _dormant_last_activity(ctx: GenContext, accts: list[Account]) -> None:
    """Give background dormant accounts one old transaction before the dataset."""
    for acct in accts:
        ts = ctx.tb.dataset_start_ts - int(ctx.rng.integers(200, 600)) * DAY_S
        cp = ctx.pick("bank")
        ctx.ledger.add(acct.id, ts, CREDIT, int(ctx.rng.integers(500, 5000)) * 100, "neft", "counterparty", cp, ctx.cp_name(cp), "Savings interest credit")

"""Shared generation state: RNG, names, entity registries and the ledger.

One ``GenContext`` is created per seed run by ``datagen/cli.py`` and passed to
the population factory and every scenario. It never touches the database;
``writers.py`` turns its contents into documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
from faker import Faker

from backend.app.domain.enums import IdPrefix
from datagen.factories.names import NameFactory
from datagen.ledger import LedgerBuilder
from datagen.timebase import DAY_S, Timebase


@dataclass
class Counterparty:
    """External party outside the bank."""

    id: str
    kind: str
    display_name: str
    vpa: str | None
    bank_ifsc: str | None
    first_seen_ts: int


@dataclass
class Customer:
    """KYC profile of a bank customer."""

    id: str
    name: str
    dob: date
    occupation: str
    declared_income: int  # rupees per year
    city: str
    kyc_status: str
    kyc_refreshed_ts: int | None
    risk_rating: str


@dataclass
class Account:
    """A bank account at our bank."""

    id: str
    customer_id: str
    account_no: str
    ifsc: str
    vpa: str | None
    type: str
    status: str
    opened_ts: int
    branch: str
    declared_turnover: int | None  # rupees per month
    holder_name: str
    first_name: str
    persona: str  # generator-only; never written to the database
    favourites: dict[str, list[str]] = field(default_factory=dict)


class IdAllocator:
    """Random, unique readable ids, so id order carries no generation hint."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self._used: dict[str, set[int]] = {}

    def next(self, prefix: str, digits: int = 6) -> str:
        used = self._used.setdefault(prefix, set())
        high = 10**digits - 1
        while True:
            n = int(self._rng.integers(1, high))
            if n not in used:
                used.add(n)
                return f"{prefix}{n:0{digits}d}"


@dataclass
class GenContext:
    """Everything a generator needs, plus the accumulated dataset."""

    rng: np.random.Generator
    faker: Faker
    tb: Timebase
    params: dict[str, Any]
    names: NameFactory = field(init=False)
    ids: IdAllocator = field(init=False)
    ledger: LedgerBuilder = field(default_factory=LedgerBuilder)
    customers: dict[str, Customer] = field(default_factory=dict)
    accounts: dict[str, Account] = field(default_factory=dict)
    counterparties: dict[str, Counterparty] = field(default_factory=dict)
    pools: dict[str, list[str]] = field(default_factory=dict)
    complaints: list[dict[str, Any]] = field(default_factory=list)
    truth: list[dict[str, Any]] = field(default_factory=list)
    base_opening: dict[str, int] = field(default_factory=dict)
    background_accounts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.names = NameFactory(self.rng, self.faker)
        self.ids = IdAllocator(self.rng)

    # --- registries -----------------------------------------------------------

    def new_counterparty(
        self, kind: str, name: str, *, vpa: str | None = None, ifsc: str | None = None, pool: str | None = None
    ) -> str:
        cid = self.ids.next(IdPrefix.COUNTERPARTY.value)
        first_seen = self.tb.dataset_start_ts - int(self.rng.integers(0, 700)) * DAY_S
        self.counterparties[cid] = Counterparty(cid, kind, name, vpa, ifsc, first_seen)
        if pool:
            self.pools.setdefault(pool, []).append(cid)
        return cid

    def new_individual(self, pool: str | None = "individual") -> str:
        first, last = self.names.person()
        return self.new_counterparty(
            "individual", f"{first} {last}", vpa=self.names.vpa(first, last), ifsc=self.names.ifsc(False), pool=pool
        )

    def new_customer(
        self,
        occupation: str,
        declared_income: int,
        *,
        age_range: tuple[int, int] = (24, 60),
        kyc_status: str = "verified",
        kyc_refreshed_ts: int | None = None,
        risk_rating: str | None = None,
    ) -> tuple[Customer, str, str]:
        """Create a customer; returns ``(customer, first, last)``."""
        first, last = self.names.person()
        age = int(self.rng.integers(age_range[0], age_range[1] + 1))
        dob = date(self.tb.as_of.year - age, int(self.rng.integers(1, 13)), int(self.rng.integers(1, 29)))
        if kyc_refreshed_ts is None and kyc_status == "verified":
            kyc_refreshed_ts = self.tb.dataset_start_ts - int(self.rng.integers(30, 900)) * DAY_S
        rating = risk_rating or str(self.rng.choice(["low", "low", "low", "medium", "medium", "high"]))
        cust = Customer(
            id=self.ids.next(IdPrefix.CUSTOMER.value),
            name=f"{first} {last}",
            dob=dob,
            occupation=occupation,
            declared_income=declared_income,
            city=self.names.city(),
            kyc_status=kyc_status,
            kyc_refreshed_ts=kyc_refreshed_ts,
            risk_rating=rating,
        )
        self.customers[cust.id] = cust
        return cust, first, last

    def new_account(
        self,
        customer: Customer,
        first: str,
        last: str,
        *,
        persona: str,
        opened_ts: int,
        declared_turnover: int | None,
        acct_type: str = "savings",
        holder_name: str | None = None,
        with_vpa: bool = True,
        base_opening_paise: int = 0,
    ) -> Account:
        acct = Account(
            id=self.ids.next(IdPrefix.ACCOUNT.value),
            customer_id=customer.id,
            account_no=self.names.account_no(),
            ifsc=self.names.ifsc(True),
            vpa=self.names.vpa(first, last) if with_vpa else None,
            type=acct_type,
            status="active",
            opened_ts=opened_ts,
            branch=f"{customer.city} Main",
            declared_turnover=declared_turnover,
            holder_name=holder_name or customer.name,
            first_name=first,
            persona=persona,
        )
        self.accounts[acct.id] = acct
        if opened_ts < self.tb.dataset_start_ts:
            self.base_opening[acct.id] = base_opening_paise
        return acct

    def pick(self, pool: str, n: int | None = None, replace: bool = False) -> Any:
        """Pick one (``n`` is None) or ``n`` counterparty ids from a pool."""
        items = self.pools[pool]
        if n is None:
            return items[int(self.rng.integers(len(items)))]
        idx = self.rng.choice(len(items), size=min(n, len(items)) if not replace else n, replace=replace)
        return [items[int(i)] for i in idx]

    def cp_name(self, cp_id: str) -> str:
        return self.counterparties[cp_id].display_name

    def opened_in_dataset(self) -> dict[str, int]:
        return {a.id: a.opened_ts for a in self.accounts.values() if a.opened_ts >= self.tb.dataset_start_ts}

    def add_truth(self, account_id: str, scenario_type: str, label: str, expected: str, signals: list[str]) -> None:
        self.truth.append(
            {
                "account_id": account_id,
                "scenario_type": scenario_type,
                "label": label,
                "expected_disposition": expected,
                "planted_signals": signals,
                "expected_evidence_keys": [f"signal:{s}" for s in signals],
            }
        )

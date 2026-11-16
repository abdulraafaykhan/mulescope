"""Indian names, VPAs, IFSC codes, account numbers and merchant brands.

All randomness comes from the seeded NumPy generator or the Faker instance
seeded from it. Uniqueness of VPAs and account numbers is enforced here.
Used by the counterparty, customer and scenario factories.
"""

from __future__ import annotations

import re

import numpy as np
from faker import Faker

OUR_BANK_PREFIX = "DEMO"
OTHER_BANK_PREFIXES = ("HDXC", "ICXC", "SBXN", "AXXB", "KKXB", "PNXB", "BRXB", "YSXB")
VPA_HANDLES = ("demo", "okdemo", "ybldemo", "ibldemo", "axldemo")

CITIES = (
    "Mumbai", "Pune", "Bengaluru", "Hyderabad", "Chennai", "Delhi", "Noida", "Gurugram",
    "Kolkata", "Ahmedabad", "Jaipur", "Lucknow", "Indore", "Nagpur", "Surat", "Kochi",
    "Coimbatore", "Bhopal", "Patna", "Chandigarh",
)

BRANDS: dict[str, tuple[str, ...]] = {
    "food": ("Swiggy", "Zomato", "Domino's Pizza", "Haldiram's", "Chai Point", "Burger King", "McDonald's", "Saravana Bhavan", "Wow Momo", "Behrouz Biryani"),
    "grocery": ("BigBasket", "Blinkit", "Zepto", "DMart", "Reliance Fresh", "More Supermarket", "Spencer's", "JioMart"),
    "utility": ("BESCOM", "MSEDCL", "Tata Power", "Adani Electricity", "BWSSB", "Mahanagar Gas", "Indraprastha Gas", "ACT Fibernet", "Airtel Xstream", "TNEB"),
    "fuel": ("HPCL", "IOCL", "BPCL", "Shell", "Nayara Energy"),
    "retail": ("Amazon", "Flipkart", "Myntra", "Croma", "Reliance Digital", "Decathlon", "Lifestyle", "Nykaa", "Ajio", "Tata CLiQ"),
    "medical": ("Apollo Pharmacy", "MedPlus", "Tata 1mg", "Netmeds", "Wellness Forever"),
    "recharge": ("Jio Prepaid", "Airtel Prepaid", "Vi Prepaid"),
    "platform": ("Swiggy Partner Payout", "Zomato Partner Payout", "Uber India", "Ola Driver Payout", "Rapido Captain", "Urban Company Payout", "Porter Payout", "Zepto Rider Payout"),
    "wallet": ("Paytm Wallet", "PhonePe Wallet", "Amazon Pay Wallet", "MobiKwik Wallet"),
    "lender": ("HDFC Bank Loans", "Bajaj Finance", "ICICI Home Loans", "Tata Capital", "SBI Auto Loan", "Axis Personal Loan"),
    "pension": ("CPAO Pension", "State Treasury Pension", "EPFO Pension"),
    "travel": ("MakeMyTrip", "Yatra Travels", "Thomas Cook India", "Cleartrip", "IRCTC"),
    "bank": ("DEMO Bank FD Maturity", "DEMO Bank RD Maturity", "Sub-Registrar Escrow"),
    "gov": ("GSTN Payment",),
}

EMPLOYER_SUFFIX = ("Technologies Pvt Ltd", "Infotech Pvt Ltd", "Industries Ltd", "Logistics Pvt Ltd", "Pharma Ltd", "Retail Pvt Ltd", "Consultancy LLP", "Textiles Pvt Ltd", "Foods Pvt Ltd", "Engineering Works")
SUPPLIER_SUFFIX = ("Traders", "Wholesale", "Distributors", "Enterprises", "Agencies", "Suppliers")
VENDOR_SUFFIX = ("Caterers", "Decorators", "Tent House", "Security Services", "Electricals", "Sound & Lights")


class NameFactory:
    """Seeded source of Indian-context identifiers.

    Args:
        rng: The dataset RNG.
        faker: Faker seeded from ``rng`` with the ``en_IN`` locale.
    """

    def __init__(self, rng: np.random.Generator, faker: Faker) -> None:
        self.rng = rng
        self.faker = faker
        self._vpas: set[str] = set()
        self._account_nos: set[str] = set()

    def person(self) -> tuple[str, str]:
        """Return ``(first, last)`` for an Indian person."""
        return self.faker.first_name(), self.faker.last_name()

    def city(self) -> str:
        return str(self.rng.choice(CITIES))

    def _slug(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())[:14] or "user"

    def vpa(self, first: str, last: str | None = None) -> str:
        """Return a unique VPA like ``priya.sharma42@okdemo``."""
        base = self._slug(first) + ("." + self._slug(last) if last else "")
        while True:
            handle = VPA_HANDLES[int(self.rng.integers(len(VPA_HANDLES)))]
            candidate = f"{base}{int(self.rng.integers(1, 999))}@{handle}"
            if candidate not in self._vpas:
                self._vpas.add(candidate)
                return candidate

    def ifsc(self, ours: bool) -> str:
        prefix = OUR_BANK_PREFIX if ours else OTHER_BANK_PREFIXES[int(self.rng.integers(len(OTHER_BANK_PREFIXES)))]
        return f"{prefix}0{int(self.rng.integers(0, 999_999)):06d}"

    def account_no(self) -> str:
        """Return a unique 12-digit account number."""
        while True:
            candidate = f"{int(self.rng.integers(10**11, 10**12 - 1))}"
            if candidate not in self._account_nos:
                self._account_nos.add(candidate)
                return candidate

    def pan_masked(self) -> str:
        letter = "ABCDEFGHJKLMNPQRSTUVWXYZ"[int(self.rng.integers(24))]
        return f"XXXXX{int(self.rng.integers(1000, 9999))}{letter}"

    def employer(self) -> str:
        return f"{self.faker.last_name()} {EMPLOYER_SUFFIX[int(self.rng.integers(len(EMPLOYER_SUFFIX)))]}"

    def supplier(self) -> str:
        return f"{self.faker.last_name()} {SUPPLIER_SUFFIX[int(self.rng.integers(len(SUPPLIER_SUFFIX)))]}"

    def vendor(self) -> str:
        return f"{self.faker.last_name()} {VENDOR_SUFFIX[int(self.rng.integers(len(VENDOR_SUFFIX)))]}"

    def upi_ref(self) -> str:
        return f"{int(self.rng.integers(10**11, 10**12 - 1))}"

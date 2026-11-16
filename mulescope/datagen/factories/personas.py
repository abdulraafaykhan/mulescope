"""Customer personas and their transaction templates (build prompt section 6.1).

Each persona is data: occupations, income, how much turnover it declares,
the time-of-day curve and a list of transaction templates. The vectorised
engine in ``background.py`` turns templates into ledger rows. Amounts are in
rupees here; the engine converts to paise.

Counterparty specs (``cp``):
    ("fav", key, pool, k)  one of the account's k favourite parties from a pool
    ("pool", pool)         any party from a pool
    ("atm",)               ATM withdrawal in the account's city
    ("p2p", internal_p)    a friend: internal bank account with probability
                           ``internal_p`` (double entry), else external
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HOUR_CURVES: dict[str, tuple[float, ...]] = {
    # 00..23 IST
    "evening": (1, 0.5, 0.3, 0.2, 0.2, 0.4, 1, 2, 3, 3, 3, 3, 4, 4, 3, 3, 3, 4, 6, 8, 9, 8, 5, 2),
    "daytime": (0.2, 0.1, 0.1, 0.1, 0.1, 0.3, 1, 3, 6, 8, 9, 9, 8, 8, 8, 8, 8, 8, 7, 6, 4, 2, 1, 0.5),
    "spread": (2, 1.5, 1, 1, 1, 2, 3, 4, 5, 5, 5, 6, 7, 6, 5, 5, 5, 6, 7, 8, 8, 7, 5, 3),
    "bank": (0, 0, 0, 0, 0, 0, 0, 0.5, 2, 6, 8, 7, 5, 4, 3, 3, 2, 1, 0.5, 0, 0, 0, 0, 0),
    "morning": (0.2, 0.1, 0.1, 0.1, 0.3, 1, 4, 7, 8, 8, 7, 6, 5, 4, 4, 3, 3, 3, 3, 2, 1.5, 1, 0.5, 0.3),
}

UPI_P2P = ("UPI/P2P/{ref}/{cp}", "UPI/{ref}/{cp}/Sent via app", "UPI/P2P/{ref}/{cp}/thanks")
UPI_MERCHANT = ("UPI/P2M/{ref}/{cp}", "UPI/{ref}/{cp}/Payment")


@dataclass(frozen=True)
class Template:
    """One recurring kind of transaction for a persona."""

    name: str
    kind: str  # "monthly" | "poisson" | "members"
    sign: int  # +1 credit, -1 debit
    rate: float  # events per month (poisson) or probability per month (monthly/members)
    median: float  # rupees
    sigma: float
    channels: tuple[tuple[str, float], ...]
    cp: tuple[Any, ...]
    remarks: tuple[str, ...]
    day: tuple[int, int] = (1, 28)
    round_to: int = 0
    p_round: float = 0.0
    paise: bool = False
    include_prob: float = 1.0
    weekend_boost: float = 1.0
    festival_mult: float = 1.0
    hours: str | None = None


@dataclass(frozen=True)
class Persona:
    """A behaviour profile shared by many customers."""

    name: str
    occupations: tuple[str, ...]
    income: tuple[int, int]  # annual rupees
    turnover_factor: float  # declared monthly turnover = income / 12 * factor
    hours: str
    templates: tuple[Template, ...]
    opening_months: float = 1.5
    acct_type: str = "savings"
    age: tuple[int, int] = (24, 58)
    second_account_p: float = 0.12
    extra: dict[str, Any] = field(default_factory=dict)


def _t(**kw: Any) -> Template:
    return Template(**kw)


GROCERY = _t(name="grocery", kind="poisson", sign=-1, rate=4, median=650, sigma=0.7, channels=(("upi", 0.85), ("card_pos", 0.15)), cp=("fav", "grocery", "grocery", 5), remarks=UPI_MERCHANT, paise=True, weekend_boost=1.4)
FOOD = _t(name="food", kind="poisson", sign=-1, rate=3.5, median=380, sigma=0.6, channels=(("upi", 0.9), ("card_pos", 0.1)), cp=("fav", "food", "food", 5), remarks=("UPI/P2M/{ref}/{cp}", "{cp} order {ref}"), paise=True, weekend_boost=1.6, festival_mult=1.5)
BILLS = _t(name="bills", kind="poisson", sign=-1, rate=2.5, median=1100, sigma=0.5, channels=(("upi", 0.8), ("neft", 0.2)), cp=("fav", "utility", "utility", 3), remarks=("BBPS/{cp}/{month} bill", "UPI/{ref}/{cp} bill payment"), paise=True)
RECHARGE = _t(name="recharge", kind="poisson", sign=-1, rate=1, median=299, sigma=0.3, channels=(("upi", 1.0),), cp=("pool", "recharge"), remarks=("Recharge {cp} {ref}",), round_to=1, p_round=1.0)
ATM = _t(name="atm", kind="poisson", sign=-1, rate=1.2, median=3000, sigma=0.5, channels=(("atm", 1.0),), cp=("atm",), remarks=("ATM WDL {city} {ref}",), round_to=500, p_round=1.0)
CARD = _t(name="card", kind="poisson", sign=-1, rate=2, median=1800, sigma=0.8, channels=(("card_pos", 1.0),), cp=("fav", "retail", "retail", 4), remarks=("POS {cp} {city}",), paise=True, weekend_boost=1.5, festival_mult=1.8)
P2P_OUT = _t(name="p2p_out", kind="poisson", sign=-1, rate=1.5, median=1500, sigma=0.8, channels=(("upi", 0.9), ("imps", 0.1)), cp=("p2p", 0.3), remarks=UPI_P2P, round_to=100, p_round=0.7)
P2P_IN = _t(name="p2p_in", kind="poisson", sign=1, rate=0.8, median=1200, sigma=0.8, channels=(("upi", 0.9), ("imps", 0.1)), cp=("p2p", 0.3), remarks=UPI_P2P, round_to=100, p_round=0.7)
WALLET = _t(name="wallet", kind="poisson", sign=-1, rate=0.4, median=1000, sigma=0.4, channels=(("wallet_load", 1.0),), cp=("pool", "wallet"), remarks=("Wallet load {cp} {ref}",), round_to=500, p_round=1.0)
FESTIVAL_FUND = _t(name="festival_fund", kind="monthly", sign=-1, rate=0.25, median=501, sigma=0.4, channels=(("upi", 1.0),), cp=("p2p", 0.0), remarks=("Ganesh Chaturthi fund", "Navratri pooja contribution", "Society festival contribution"), day=(5, 15), round_to=101, p_round=1.0)

PERSONAS: dict[str, Persona] = {
    "salaried": Persona(
        name="salaried",
        occupations=("Software engineer", "Accountant", "Sales executive", "School teacher", "Bank clerk", "Staff nurse", "HR executive", "Civil engineer", "Marketing manager"),
        income=(360_000, 1_800_000), turnover_factor=1.3, hours="evening", opening_months=1.2,
        templates=(
            _t(name="salary", kind="monthly", sign=1, rate=1.0, median=0, sigma=0.02, channels=(("neft", 1.0),), cp=("fav", "employer", "employer", 1), remarks=("SALARY {month} {cp}", "NEFT/SAL/{ref}/{cp}"), day=(1, 2), hours="bank"),
            _t(name="rent", kind="monthly", sign=-1, rate=0.95, median=14000, sigma=0.4, channels=(("upi", 0.6), ("neft", 0.4)), cp=("fav", "landlord", "individual", 1), remarks=("Rent {month}", "UPI/{ref}/{cp}/Rent {month}"), day=(3, 6), round_to=500, p_round=1.0, include_prob=0.6),
            _t(name="emi", kind="monthly", sign=-1, rate=1.0, median=9000, sigma=0.5, channels=(("neft", 1.0),), cp=("fav", "lender", "lender", 1), remarks=("NACH/EMI/{cp}/{ref}",), day=(5, 7), include_prob=0.45, hours="bank"),
            GROCERY, FOOD, BILLS, RECHARGE, ATM, CARD, P2P_OUT, P2P_IN, WALLET, FESTIVAL_FUND,
        ),
    ),
    "small_business": Persona(
        name="small_business",
        occupations=("Kirana store owner", "Mobile accessories shop owner", "Garment retailer", "Hardware shop owner", "Stationery shop owner"),
        income=(300_000, 1_200_000), turnover_factor=4.0, hours="daytime", opening_months=1.0, acct_type="current",
        templates=(
            _t(name="sales", kind="poisson", sign=1, rate=28, median=480, sigma=0.8, channels=(("upi", 1.0),), cp=("fav", "customers", "individual", 35), remarks=("UPI/P2M/{ref}/{cp}", "UPI/{ref}/{cp}/Paid via QR"), paise=True, weekend_boost=1.3),
            _t(name="supplier", kind="poisson", sign=-1, rate=3, median=6500, sigma=0.5, channels=(("neft", 0.5), ("imps", 0.5)), cp=("fav", "supplier", "supplier", 4), remarks=("NEFT/{ref}/{cp}/stock", "IMPS/P2A/{ref}/{cp}/inv"), round_to=10, p_round=0.6),
            _t(name="gst", kind="monthly", sign=-1, rate=0.9, median=2200, sigma=0.5, channels=(("neft", 1.0),), cp=("pool", "gov"), remarks=("GST payment {month}", "GSTN/CPIN/{ref}"), day=(18, 20), hours="bank"),
            _t(name="shop_rent", kind="monthly", sign=-1, rate=1.0, median=9000, sigma=0.4, channels=(("neft", 0.5), ("upi", 0.5)), cp=("fav", "landlord", "individual", 1), remarks=("Shop rent {month}",), day=(2, 6), round_to=500, p_round=1.0),
            ATM, BILLS, P2P_OUT, GROCERY,
        ),
    ),
    "freelancer": Persona(
        name="freelancer",
        occupations=("Freelance graphic designer", "Freelance developer", "Content writer", "Photographer", "Video editor"),
        income=(420_000, 1_500_000), turnover_factor=1.4, hours="spread",
        templates=(
            _t(name="client", kind="poisson", sign=1, rate=1.6, median=32000, sigma=0.5, channels=(("neft", 0.6), ("imps", 0.4)), cp=("fav", "client", "client", 4), remarks=("NEFT/{ref}/{cp}/invoice", "IMPS/{ref}/{cp}/Inv {month}"), round_to=1000, p_round=0.8, hours="bank"),
            _t(name="vendor", kind="poisson", sign=-1, rate=0.8, median=7000, sigma=0.5, channels=(("upi", 0.5), ("imps", 0.5)), cp=("p2p", 0.0), remarks=("UPI/{ref}/{cp}/project share",), round_to=500, p_round=0.8),
            _t(name="tax", kind="monthly", sign=-1, rate=0.33, median=12000, sigma=0.4, channels=(("neft", 1.0),), cp=("pool", "gov"), remarks=("Advance tax challan {ref}",), day=(10, 15), round_to=100, p_round=1.0),
            _t(name="rent", kind="monthly", sign=-1, rate=0.95, median=13000, sigma=0.4, channels=(("upi", 1.0),), cp=("fav", "landlord", "individual", 1), remarks=("Rent {month}",), day=(2, 6), round_to=500, p_round=1.0),
            GROCERY, FOOD, BILLS, CARD, WALLET,
        ),
    ),
    "student": Persona(
        name="student", occupations=("Student",), income=(0, 60_000), turnover_factor=1.0, hours="evening", opening_months=0, age=(18, 23), second_account_p=0.0,
        templates=(
            _t(name="allowance", kind="monthly", sign=1, rate=0.95, median=5000, sigma=0.4, channels=(("upi", 0.8), ("imps", 0.2)), cp=("fav", "family", "individual", 1), remarks=("UPI/{ref}/{cp}/pocket money", "UPI/P2P/{ref}/{cp}"), day=(1, 5), round_to=500, p_round=1.0),
            _t(name="spends", kind="poisson", sign=-1, rate=9, median=160, sigma=0.7, channels=(("upi", 1.0),), cp=("fav", "food", "food", 4), remarks=UPI_MERCHANT, paise=True, weekend_boost=1.4),
            RECHARGE,
            _t(name="atm_small", kind="poisson", sign=-1, rate=0.4, median=1000, sigma=0.3, channels=(("atm", 1.0),), cp=("atm",), remarks=("ATM WDL {city} {ref}",), round_to=500, p_round=1.0),
            _t(name="friends", kind="poisson", sign=-1, rate=1.0, median=300, sigma=0.6, channels=(("upi", 1.0),), cp=("p2p", 0.2), remarks=UPI_P2P, round_to=10, p_round=0.6),
        ),
    ),
    "homemaker": Persona(
        name="homemaker", occupations=("Homemaker",), income=(0, 120_000), turnover_factor=1.0, hours="morning", opening_months=0, age=(26, 60), second_account_p=0.0,
        templates=(
            _t(name="household", kind="monthly", sign=1, rate=0.95, median=14000, sigma=0.4, channels=(("upi", 0.7), ("imps", 0.3)), cp=("fav", "family", "individual", 1), remarks=("UPI/{ref}/{cp}/household", "IMPS/{ref}/{cp}/home exp"), day=(1, 4), round_to=1000, p_round=1.0),
            GROCERY,
            _t(name="family_credit", kind="poisson", sign=1, rate=0.3, median=4000, sigma=0.5, channels=(("upi", 1.0),), cp=("fav", "relatives", "individual", 3), remarks=UPI_P2P, round_to=500, p_round=1.0),
            BILLS, P2P_OUT, FESTIVAL_FUND,
        ),
    ),
    "retired": Persona(
        name="retired", occupations=("Retired government employee", "Retired teacher", "Retired bank officer"), income=(240_000, 720_000), turnover_factor=1.2, hours="morning", opening_months=4, age=(61, 78),
        templates=(
            _t(name="pension", kind="monthly", sign=1, rate=1.0, median=0, sigma=0.01, channels=(("neft", 1.0),), cp=("fav", "pension", "pension", 1), remarks=("PENSION {month} {cp}",), day=(1, 2), hours="bank"),
            _t(name="medical", kind="poisson", sign=-1, rate=1.6, median=1400, sigma=0.6, channels=(("upi", 0.6), ("card_pos", 0.4)), cp=("fav", "medical", "medical", 2), remarks=UPI_MERCHANT, paise=True),
            BILLS,
            _t(name="atm_ret", kind="poisson", sign=-1, rate=1.0, median=5000, sigma=0.4, channels=(("atm", 1.0),), cp=("atm",), remarks=("ATM WDL {city} {ref}",), round_to=500, p_round=1.0),
            _t(name="to_family", kind="poisson", sign=-1, rate=0.4, median=5000, sigma=0.5, channels=(("upi", 0.5), ("neft", 0.5)), cp=("fav", "family", "individual", 2), remarks=UPI_P2P, round_to=500, p_round=1.0),
        ),
    ),
    "gig_worker": Persona(
        name="gig_worker", occupations=("Delivery partner", "Cab driver", "Bike taxi rider"), income=(180_000, 420_000), turnover_factor=1.3, hours="spread", opening_months=0.3, age=(20, 40),
        templates=(
            _t(name="payout", kind="poisson", sign=1, rate=11, median=850, sigma=0.5, channels=(("imps", 0.6), ("upi", 0.4)), cp=("fav", "platform", "platform", 2), remarks=("IMPS/{ref}/{cp}/weekly payout", "UPI/{ref}/{cp}/earnings"), paise=True),
            _t(name="fuel", kind="poisson", sign=-1, rate=7, median=300, sigma=0.4, channels=(("upi", 0.8), ("card_pos", 0.2)), cp=("fav", "fuel", "fuel", 2), remarks=("UPI/P2M/{ref}/{cp} fuel",), round_to=50, p_round=0.6),
            RECHARGE, FOOD,
            _t(name="atm_gig", kind="poisson", sign=-1, rate=1.0, median=1500, sigma=0.4, channels=(("atm", 1.0),), cp=("atm",), remarks=("ATM WDL {city} {ref}",), round_to=500, p_round=1.0),
            _t(name="bike_emi", kind="monthly", sign=-1, rate=1.0, median=3200, sigma=0.2, channels=(("neft", 1.0),), cp=("fav", "lender", "lender", 1), remarks=("NACH/EMI/{cp}/{ref}",), day=(5, 7), include_prob=0.5, hours="bank"),
        ),
    ),
    "professional": Persona(
        name="professional", occupations=("Doctor", "Chartered accountant", "Advocate", "Dentist", "Architect"), income=(1_200_000, 3_600_000), turnover_factor=1.6, hours="daytime", opening_months=4,
        templates=(
            _t(name="fees", kind="poisson", sign=1, rate=10, median=1800, sigma=0.6, channels=(("upi", 0.7), ("imps", 0.2), ("neft", 0.1)), cp=("pool", "individual"), remarks=("UPI/{ref}/{cp}/consultation", "UPI/P2P/{ref}/{cp}/fees"), round_to=100, p_round=0.7),
            _t(name="staff", kind="monthly", sign=-1, rate=1.0, median=16000, sigma=0.3, channels=(("neft", 1.0),), cp=("fav", "staff", "individual", 1), remarks=("Salary {month} staff",), day=(1, 3), round_to=500, p_round=1.0, hours="bank"),
            _t(name="office_rent", kind="monthly", sign=-1, rate=1.0, median=28000, sigma=0.3, channels=(("neft", 1.0),), cp=("fav", "landlord", "individual", 1), remarks=("Office rent {month}",), day=(2, 5), round_to=1000, p_round=1.0),
            CARD, BILLS, FOOD, P2P_OUT, WALLET,
        ),
    ),
    "treasurer": Persona(
        name="treasurer", occupations=("Housing society treasurer", "Temple trust treasurer", "RWA treasurer"), income=(300_000, 900_000), turnover_factor=1.0, hours="evening", opening_months=1, acct_type="current", second_account_p=0.0,
        extra={"members": (18, 32), "member_amount": (1500, 3500)},
        templates=(
            _t(name="maintenance", kind="members", sign=1, rate=0.85, median=0, sigma=0, channels=(("upi", 0.8), ("neft", 0.2)), cp=("fav", "members", "individual", 0), remarks=("Maintenance {month}", "UPI/{ref}/{cp}/society dues {month}"), day=(1, 10)),
            _t(name="vendors", kind="poisson", sign=-1, rate=2.0, median=9000, sigma=0.4, channels=(("neft", 1.0),), cp=("fav", "vendor", "vendor", 3), remarks=("NEFT/{ref}/{cp}/{month} services",), round_to=100, p_round=0.8, hours="bank"),
            BILLS,
        ),
    ),
    "dormant": Persona(
        name="dormant", occupations=("Farmer", "Retired", "Shopkeeper (inactive)"), income=(120_000, 360_000), turnover_factor=1.0, hours="daytime", opening_months=2, age=(35, 75), second_account_p=0.0,
        # Truly dormant: only one old transaction before the dataset (see background.py).
        templates=(),
    ),
}

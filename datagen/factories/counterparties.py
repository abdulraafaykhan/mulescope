"""Builds the external counterparty pools (about 600 parties).

Individuals (P2P, landlords, family, customers of sellers, victims), merchants
by category, employers, suppliers, clients, platforms, wallets, lenders,
pension offices, travel agents, vendors and a few bank/government accounts.
Called once by ``datagen/cli.py`` before any account is generated.
"""

from __future__ import annotations

from datagen.context import GenContext
from datagen.factories.names import BRANDS


def build_counterparty_pools(ctx: GenContext) -> None:
    """Populate ``ctx.pools`` using the sizes in ``scenarios.yaml``."""
    sizes: dict[str, int] = ctx.params["population"]["counterparty_pools"]
    names = ctx.names

    for _ in range(sizes["individual"]):
        ctx.new_individual("individual")

    for category, brands in BRANDS.items():
        target = sizes.get(category, len(brands))
        for i in range(target):
            brand = brands[i % len(brands)]
            label = brand if i < len(brands) else f"{brand} {names.city()}"
            kind = "merchant" if category in {"food", "grocery", "utility", "fuel", "retail", "medical", "recharge", "travel"} else category
            slug = "".join(ch for ch in brand.lower() if ch.isalnum())[:12]
            vpa = names.vpa(slug) if kind == "merchant" else None
            ctx.new_counterparty(kind, label, vpa=vpa, ifsc=names.ifsc(False), pool=category)

    for _ in range(sizes["employer"]):
        ctx.new_counterparty("employer", names.employer(), ifsc=names.ifsc(False), pool="employer")
    for _ in range(sizes["supplier"]):
        ctx.new_counterparty("supplier", names.supplier(), ifsc=names.ifsc(False), pool="supplier")
    for _ in range(sizes["vendor"]):
        ctx.new_counterparty("vendor", names.vendor(), ifsc=names.ifsc(False), pool="vendor")
    for _ in range(sizes["client"]):
        ctx.new_counterparty("client", names.employer(), ifsc=names.ifsc(False), pool="client")
    for _ in range(sizes["local_shop"]):
        first, last = names.person()
        shop = f"{last} {str(ctx.rng.choice(['Kirana', 'General Store', 'Medicals', 'Sweets', 'Mobiles', 'Stationers']))}"
        ctx.new_counterparty("merchant", shop, vpa=names.vpa(last, "store"), ifsc=names.ifsc(False), pool="grocery")

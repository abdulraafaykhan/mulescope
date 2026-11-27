"""``uv run seed``: generate the synthetic dataset, load it and run the detector.

Examples (PowerShell)::

    uv run seed --seed 42 --customers 300 --reset
    uv run seed --preview ACC-123456

Only this process (and evals) loads the truth connection. Ground truth is
written to ``mulescope_truth.ground_truth`` and nowhere else.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter
from datetime import timedelta
from typing import Any

import numpy as np
from faker import Faker
from pymongo import AsyncMongoClient

from backend.app.core.clock import SystemClock
from backend.app.core.config_files import load_llm_config, load_playbook_config, load_scenarios_config, load_scoring_config
from backend.app.core.logging import configure_logging
from backend.app.core.settings import DatagenSettings
from backend.app.repositories.mongo.alerts_repo import MongoAlertRepository
from backend.app.repositories.mongo.bootstrap import ensure_collections, ensure_truth_collections
from backend.app.repositories.mongo.cases_repo import MongoCaseRepository
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.collection_names import TruthCollection
from backend.app.repositories.mongo.transactions_repo import MongoTransactionRepository
from backend.app.services.detection import PassThroughDetector
from datagen import writers
from datagen.context import GenContext
from datagen.factories.background import build_population
from datagen.factories.counterparties import build_counterparty_pools
from datagen.scenarios.base import registered_scenarios
from datagen.timebase import IST_OFFSET_S, Timebase, to_datetime
from datagen.validate import check_coverage, check_ledger

MAX_ORGANIC_ALERTS = 10


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="seed", description="Generate and load the MuleScope dataset.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--customers", type=int, default=300)
    p.add_argument("--reset", action="store_true", help="drop both databases before loading")
    p.add_argument("--preview", metavar="ACCOUNT_ID", help="print one account's 14-day story and exit")
    return p.parse_args()


def generate(seed: int, customers: int, settings: DatagenSettings, params: dict[str, Any]) -> tuple[GenContext, Any, dict[str, int]]:
    """Build the whole dataset in memory. Deterministic for a given seed."""
    ds = params["dataset"]
    tb = Timebase.build(settings.as_of_date, ds["dataset_days"], ds["window_days"], ds["history_days"])
    rng = np.random.default_rng(seed)
    faker = Faker("en_IN")
    faker.seed_instance(int(rng.integers(0, 2**31 - 1)))
    ctx = GenContext(rng=rng, faker=faker, tb=tb, params=params)
    build_counterparty_pools(ctx)

    planted = sum(v["count"] for s in params["scenarios"].values() for v in s["variants"].values())
    build_population(ctx, max(customers - planted, 0))

    per_type: dict[str, int] = {}
    for name, cls in sorted(registered_scenarios().items()):
        scenario = cls(ctx, params["scenarios"][name])
        for variant, vcfg in params["scenarios"][name]["variants"].items():
            for i in range(int(vcfg["count"])):
                scenario.build(variant, i)
                per_type[f"{name}.{variant}"] = per_type.get(f"{name}.{variant}", 0) + 1
    deposit = "Branch cash deposit"
    ledger = ctx.ledger.finalize(ctx.base_opening, ctx.opened_in_dataset(), deposit)
    return ctx, ledger, per_type


async def _load(ctx: GenContext, ledger: Any, settings: DatagenSettings, reset: bool, seed: int, batch: int) -> dict[str, int]:
    llm = load_llm_config(settings.config_dir)
    client: AsyncMongoClient[Any] = AsyncMongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    truth_client: AsyncMongoClient[Any] = AsyncMongoClient(settings.mongo_truth_uri.get_secret_value(), tz_aware=True)
    try:
        db, truth_db = client[settings.mongo_db_name], truth_client[settings.mongo_truth_db_name]
        if reset:
            await client.drop_database(settings.mongo_db_name)
            await truth_client.drop_database(settings.mongo_truth_db_name)
        await ensure_collections(db, llm.cache_ttl_seconds, llm.call_log_ttl_seconds)
        await ensure_truth_collections(truth_db)

        last_balance: dict[str, int] = dict(ledger.opening)
        for a, b in zip(ledger.cols["account"], ledger.balance_after, strict=True):
            last_balance[a] = int(b)
        counts = {
            Col.CUSTOMERS.value: await writers.insert_all(db, Col.CUSTOMERS, writers.customer_docs(ctx), batch),
            Col.ACCOUNTS.value: await writers.insert_all(db, Col.ACCOUNTS, writers.account_docs(ctx, last_balance), batch),
            Col.COUNTERPARTIES.value: await writers.insert_all(db, Col.COUNTERPARTIES, writers.counterparty_docs(ctx), batch),
            Col.TRANSACTIONS.value: await writers.insert_all(db, Col.TRANSACTIONS, writers.transaction_docs(ledger), batch),
            Col.COMPLAINTS.value: await writers.insert_all(db, Col.COMPLAINTS, writers.complaint_docs(ctx, ledger), batch),
        }
        counts["ground_truth"] = await writers.insert_all(truth_db, TruthCollection.GROUND_TRUTH, writers.truth_docs(ctx), batch)
        await db[Col.DATASET_META].replace_one(
            {"_id": f"seed-{seed}"},
            {"_id": f"seed-{seed}", "seed": seed, "generator_version": ctx.params["generator_version"], "counts": counts, "generated_at": to_datetime(ctx.tb.end_ts), "created_at": to_datetime(ctx.tb.end_ts)},
            upsert=True,
        )
        clock = SystemClock()
        detector = PassThroughDetector(MongoTransactionRepository(db), MongoAlertRepository(db), MongoCaseRepository(db), load_scoring_config(settings.config_dir), load_playbook_config(settings.config_dir), clock)
        result = await detector.detect(to_datetime(ctx.tb.end_ts))
        counts[Col.ALERTS.value] = await db[Col.ALERTS].count_documents({})
        counts[Col.CASES.value] = await db[Col.CASES].count_documents({})
        counts["_alerts_created"] = len(result.alerts_created)
        counts["_alerted_accounts"] = 0
        ctx.params["_alerted"] = {a["account_id"] for a in await MongoAlertRepository(db).list(limit=10_000)}
        return counts
    finally:
        await client.close()
        await truth_client.close()


async def _preview(settings: DatagenSettings, account_id: str) -> None:
    client: AsyncMongoClient[Any] = AsyncMongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        db = client[settings.mongo_db_name]
        acct = await db[Col.ACCOUNTS].find_one({"_id": account_id})
        if not acct:
            print(f"account {account_id} not found")
            return
        cust = await db[Col.CUSTOMERS].find_one({"_id": acct["customer_id"]}) or {}
        last = await db[Col.TRANSACTIONS].find_one({"account_id": account_id}, sort=[("ts", -1)])
        end = last["ts"] + timedelta(seconds=1) if last else None
        if end is None:
            print("no transactions")
            return
        start = end - timedelta(days=14)
        kyc = cust.get("kyc", {})
        print(f"{account_id}  {acct.get('holder_name')}  {kyc.get('occupation')}  opened {acct['opened_at']:%Y-%m-%d}  declared turnover {acct.get('declared_monthly_turnover')}")
        print(f"{'time (IST)':<17} {'dir':<6} {'amount':>12} {'channel':<12} {'counterparty':<28} {'balance':>12}  remarks")
        async for t in db[Col.TRANSACTIONS].find({"account_id": account_id, "ts": {"$gte": start, "$lt": end}}).sort("ts", 1):
            ist = t["ts"] + timedelta(seconds=IST_OFFSET_S)
            print(f"{ist:%Y-%m-%d %H:%M}  {t['direction']:<6} {float(t['amount'].to_decimal()):>12,.2f} {t['channel']:<12} {str(t['counterparty']['name'])[:28]:<28} {float(t['balance_after'].to_decimal()):>12,.2f}  {str(t['remarks'])[:60]}")
    finally:
        await client.close()


def main() -> None:
    """Entry point for ``uv run seed``."""
    args = _parse()
    configure_logging("WARNING")
    settings = DatagenSettings()
    if args.preview:
        asyncio.run(_preview(settings, args.preview))
        return
    params = load_scenarios_config(settings.config_dir)
    t0 = time.perf_counter()
    ctx, ledger, per_type = generate(args.seed, args.customers, settings, params)
    t_gen = time.perf_counter() - t0
    problems = check_ledger(ctx, ledger)
    for p in problems:
        print(f"VALIDATION ERROR: {p}")
    if problems:
        raise SystemExit(1)
    print(f"generated {len(ctx.customers)} customers, {len(ctx.accounts)} accounts, {len(ctx.counterparties)} counterparties, {len(ledger)} ledger entries in {t_gen:.1f}s")

    counts = asyncio.run(_load(ctx, ledger, settings, args.reset, args.seed, params["dataset"]["batch_size"]))
    alerted: set[str] = ctx.params.pop("_alerted")
    missing, organic, warnings = check_coverage(ctx, alerted, MAX_ORGANIC_ALERTS)

    print("\ncounts per collection:")
    for k, v in counts.items():
        if not k.startswith("_"):
            print(f"  {k:<16} {v:>8}")
    planted_by_type = Counter(t["scenario_type"] for t in ctx.truth if t["account_id"] in alerted)
    print(f"\nalerts: {counts['_alerts_created']} created ({len(alerted)} accounts alerted, {organic} organic)")
    for scenario_type, n in sorted(per_type.items()):
        print(f"  {scenario_type:<36} planted {n:>2}  alerted {planted_by_type.get(scenario_type, 0):>2}")
    if missing:
        print("\nplanted accounts with NO alert:")
        for t in missing:
            print(f"  {t['account_id']}  {t['scenario_type']}")
    else:
        print("\nall planted accounts have alerts")
    for w in warnings:
        print(f"WARNING: {w}")
    print(f"\ntotal time {time.perf_counter() - t0:.1f}s")

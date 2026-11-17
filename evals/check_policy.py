"""``uv run check-policy``: expected vs predicted disposition for the 40 planted alerts.

Code only, no LLM: metrics -> signals -> score -> disposition. Reads ground
truth from the truth database (allowed for evals), so it never runs inside the
API process. Prints a table, the accuracy and how many mules were closed.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from typing import Any

from pymongo import AsyncMongoClient

from backend.app.core.config_files import load_scoring_config
from backend.app.core.logging import configure_logging
from backend.app.core.settings import EvalsSettings
from backend.app.domain.policy.disposition import decide
from backend.app.domain.policy.scoring import score
from backend.app.repositories.mongo.accounts_repo import MongoAccountRepository, MongoComplaintRepository, MongoCustomerRepository
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.transactions_repo import MongoTransactionRepository
from backend.app.services.metrics_service import MetricsService

METRIC_COLUMNS = ("fan_in_count", "unrelated_sender_ratio", "median_exit_minutes", "pass_through_ratio", "retention_ratio", "turnover_multiple", "repeat_sender_ratio", "volume_zscore_vs_history", "beneficiary_concentration")


async def run(verbose: bool) -> None:
    settings = EvalsSettings()
    cfg = load_scoring_config(settings.config_dir)
    client: AsyncMongoClient[Any] = AsyncMongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    truth_client: AsyncMongoClient[Any] = AsyncMongoClient(settings.mongo_truth_uri.get_secret_value(), tz_aware=True)
    try:
        db = client[settings.mongo_db_name]
        truth = [t async for t in truth_client[settings.mongo_truth_db_name].ground_truth.find().sort("scenario_type", 1)]
        alerts = {a["account_id"]: a async for a in db[Col.ALERTS].find()}
        svc = MetricsService(MongoTransactionRepository(db), MongoAccountRepository(db), MongoCustomerRepository(db), MongoComplaintRepository(db), cfg)
        if not truth:
            print(f"no ground truth in {settings.mongo_truth_db_name}; seed the dataset first (uv run seed --seed 42 --customers 300 --reset)")
            return
        correct = 0
        mules_closed = 0
        confusion: Counter[tuple[str, str]] = Counter()
        print(f"{'scenario':<34} {'account':<11} {'expected':<10} {'predicted':<10} {'score':>5}  signals | mitigators")
        for t in truth:
            alert = alerts.get(t["account_id"])
            if alert is None:
                print(f"{t['scenario_type']:<34} {t['account_id']:<11} {t['expected_disposition']:<10} {'NO ALERT':<10}")
                continue
            bundle = await svc.compute(t["account_id"], alert["window"]["start"], alert["window"]["end"])
            result = decide(score(bundle.metrics, cfg), bundle.metrics, cfg)
            predicted = result.disposition.value
            ok = predicted == t["expected_disposition"]
            correct += ok
            confusion[(t["expected_disposition"], predicted)] += 1
            if t["label"] == "mule" and predicted == "close":
                mules_closed += 1
            mark = " " if ok else "X"
            print(f"{mark}{t['scenario_type']:<33} {t['account_id']:<11} {t['expected_disposition']:<10} {predicted:<10} {result.score:>5.0f}  {','.join(result.fired_signals)} | {','.join(result.mitigators)}")
            if verbose or not ok:
                m = bundle.metrics
                print("     " + "  ".join(f"{k}={getattr(m, k)}" for k in METRIC_COLUMNS))
        n = len(truth)
        print(f"\naccuracy {correct}/{n} = {correct / n:.0%}   mules closed: {mules_closed}")
        print("confusion (expected -> predicted):")
        for (exp, pred), k in sorted(confusion.items()):
            print(f"  {exp:<10} -> {pred:<10} {k}")
    finally:
        await client.close()
        await truth_client.close()


def main() -> None:
    """Entry point for ``uv run check-policy``."""
    parser = argparse.ArgumentParser(prog="check-policy")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    configure_logging("WARNING")
    asyncio.run(run(args.verbose))

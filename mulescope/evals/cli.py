"""``uv run evals --mode fallback|live``: run the planted alerts end to end and score them.

Reads ground truth from the truth database (only datagen and evals may), runs
each alert through the graph in the chosen LLM mode with auto-approve, and
stores ``eval_runs`` / ``eval_results`` in the operational database for the
Evals page. ``--resume`` continues the latest unfinished run of that mode (or
a given run id), skipping cases already evaluated, which is how a live run is
spread across free-tier quota windows.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from pymongo import AsyncMongoClient, MongoClient

from backend.app.core.logging import configure_logging
from backend.app.core.settings import EvalsSettings
from backend.app.core.wiring import build_app_objects
from backend.app.domain.enums import LlmMode
from backend.app.graph.checkpoint import build_checkpointer
from evals.harness import EvalHarness


def _print_result(r: dict[str, Any]) -> None:
    mark = "ERR" if r.get("error") else (" ok" if r["correct"] else "  X")
    detail = r["error"] if r.get("error") else f"{r['predicted'] or '-':<10} score {r['score'] if r['score'] is not None else '-':>5}  cites {r['citations']:>3} bad {r['invalid_citations']}  {r['latency_ms'] / 1000:5.1f}s  tok {r['tokens']}"
    print(f"{mark} {r['scenario_type']:<34} {r['case_id'] or r['account_id']:<10} exp {r['expected']:<10} {detail}", flush=True)


def _print_summary(run_id: str, m: dict[str, Any]) -> None:
    print(f"\neval run {run_id}  status {m['status']}")
    print(f"  accuracy {m['correct']}/{m['evaluated']} = {m['accuracy']:.1%}   mules closed {m['mules_closed']}   errors {m['errors']}")
    print(f"  citation validity {m['citation_validity']:.1%}   claim coverage {m['claim_coverage']:.1%}   tipping-off {m['tipping_off_violations']}   injection obeyed {m['injection_obeyed']}")
    print(f"  fallback rate {m['fallback_rate']:.0%}   latency p50 {m['latency_ms_p50'] / 1000:.1f}s p95 {m['latency_ms_p95'] / 1000:.1f}s   tokens {m['tokens_total']} ({m['tokens_per_case']:.0f}/case)")
    print("  confusion (expected -> predicted):")
    for exp, row in m["confusion"].items():
        print(f"    {exp:<10} " + "  ".join(f"{p}={n}" for p, n in row.items()))
    if m["status"] != "completed":
        print(f"  some cases are missing or errored; continue with: uv run evals --mode <mode> --resume {run_id}")


async def run(mode: str, resume: str | None, limit: int | None) -> None:
    s = EvalsSettings(llm_mode=LlmMode(mode))
    client: AsyncMongoClient[Any] = AsyncMongoClient(s.mongo_uri.get_secret_value(), tz_aware=True)
    truth_client: AsyncMongoClient[Any] = AsyncMongoClient(s.mongo_truth_uri.get_secret_value(), tz_aware=True)
    sync_client: MongoClient[Any] = await asyncio.to_thread(MongoClient, s.mongo_uri.get_secret_value())
    try:
        db = client[s.mongo_db_name]
        truth = [t async for t in truth_client[s.mongo_truth_db_name].ground_truth.find().sort("scenario_type", 1)]
        if limit:
            truth = truth[:limit]
        if not truth:
            print("no ground truth found; run: uv run seed --seed 42 --customers 300 --reset")
            return
        saver = await asyncio.to_thread(build_checkpointer, sync_client, s.mongo_db_name, s.checkpoint_ttl_seconds)
        app = build_app_objects(db, saver, config_dir=s.config_dir, graph_version=s.graph_version, llm_mode=s.llm_mode.value)
        harness = EvalHarness(app, db, truth)
        run_id, done = await harness.open_run(mode, resume, s.graph_version)
        print(f"eval run {run_id}  mode {mode}  {len(truth)} planted alerts, {len(done)} already evaluated", flush=True)
        results = await harness.evaluate(run_id, done, _print_result)
        _print_summary(run_id, await harness.close_run(run_id, results))
    finally:
        await client.close()
        await truth_client.close()
        await asyncio.to_thread(sync_client.close)


def main() -> None:
    """Entry point for ``uv run evals``."""
    parser = argparse.ArgumentParser(prog="evals", description="Run the planted alerts through the graph and score them.")
    parser.add_argument("--mode", choices=[m.value for m in LlmMode], default=LlmMode.FALLBACK.value)
    parser.add_argument("--resume", nargs="?", const="latest", default=None, help="continue the latest unfinished run of this mode, or the given eval run id")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N planted alerts (quick checks)")
    args = parser.parse_args()
    configure_logging("WARNING")
    asyncio.run(run(args.mode, args.resume, args.limit))

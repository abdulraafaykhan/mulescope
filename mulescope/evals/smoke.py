"""``uv run smoke``: one mule alert and one seller alert through the graph.

Runs in-process in the configured LLM mode (fallback by default), auto-approves
at the analyst gate, and prints the disposition, evidence count, actions
created and the audit-chain check. Uses the truth database only to pick the
two example cases (allowed for evals).
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

from pymongo import AsyncMongoClient, MongoClient

from backend.app.core.logging import configure_logging
from backend.app.core.settings import EvalsSettings
from backend.app.core.wiring import build_app_objects, secret
from backend.app.domain.enums import LlmMode
from backend.app.graph.checkpoint import build_checkpointer
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col

EXAMPLES = ("mule.classic", "seller.shop")


async def run(scenarios: tuple[str, ...], decision: str, mode: str | None) -> None:
    s = EvalsSettings(llm_mode=LlmMode(mode)) if mode else EvalsSettings()
    client: AsyncMongoClient[Any] = AsyncMongoClient(s.mongo_uri.get_secret_value(), tz_aware=True)
    truth: AsyncMongoClient[Any] = AsyncMongoClient(s.mongo_truth_uri.get_secret_value(), tz_aware=True)
    sync_client: MongoClient[Any] = await asyncio.to_thread(MongoClient, s.mongo_uri.get_secret_value())
    app = None
    try:
        db = client[s.mongo_db_name]
        saver = await asyncio.to_thread(build_checkpointer, sync_client, s.mongo_db_name, s.checkpoint_ttl_seconds)
        app = build_app_objects(db, saver, config_dir=s.config_dir, graph_version=s.graph_version, llm_mode=s.llm_mode.value, groq_key=secret(s.groq_api_key), gemini_key=secret(s.gemini_api_key))
        print(f"llm mode {s.llm_mode.value}; agents: " + ", ".join(f"{k}={v}" for k, v in app.deps.agents.models.items()))
        for scenario in scenarios:
            gt = await truth[s.mongo_truth_db_name].ground_truth.find_one({"scenario_type": scenario})
            if gt is None:
                print(f"{scenario}: no ground truth (run uv run seed first)")
                continue
            case = await db[Col.CASES].find_one({"account_id": gt["account_id"]})
            if case is None:
                print(f"{scenario}: no case for {gt['account_id']}")
                continue
            t0 = time.perf_counter()
            run_doc = await app.runner.start_run(case["_id"])
            run_id = run_doc["id"]
            await app.runner.wait(run_id)
            t_investigate = time.perf_counter() - t0
            status = (await app.deps.runs.get(run_id) or {}).get("status")
            if status == "awaiting_decision":
                await app.runner.decide(case["_id"], {"decision": decision, "user_id": "smoke-analyst", "role": "analyst"})
                await app.runner.wait(run_id)
            run = await app.deps.runs.get(run_id) or {}
            final_case = await app.deps.cases.get(case["_id"]) or {}
            evidence = await app.deps.evidence.for_run(case["_id"], run_id)
            actions = await app.deps.actions.for_case(case["_id"])
            report = await app.deps.reports.latest(case["_id"]) or {}
            chain = await app.audit.verify_chain(case["_id"])
            print(f"\n{scenario}  case {case['_id']}  account {gt['account_id']}  run {run_id}")
            print(f"  expected {gt['expected_disposition']}  recommended {final_case.get('recommended_disposition')}  final {final_case.get('final_disposition')}  score {final_case.get('score')}  case status {final_case.get('status')}")
            print(f"  run status {run.get('status')}  investigate {t_investigate:.1f}s  total {time.perf_counter() - t0:.1f}s  nodes latency {run.get('totals', {}).get('latency_ms')} ms")
            print(f"  evidence {len(evidence)}  report v{report.get('version')} critic {(report.get('critic') or {}).get('verdict')}  citations {len(report.get('citations') or [])}")
            print(f"  actions {len(actions)}: " + ", ".join(f"{a['type']}={a['status']}" for a in actions))
            print(f"  audit chain valid={chain['valid']} records={chain['records']}")
            execs = [e for e in await app.deps.node_execs.for_run(run_id) if e.get("agent") != "code"]
            print("  agents: " + ", ".join(f"{e['node']}={'fallback' if e.get('fallback_used') else 'llm'}({int(e.get('tokens_in') or 0) + int(e.get('tokens_out') or 0)} tok{', cache' if e.get('cache_hit') else ''})" for e in execs))
            if (report.get("critic") or {}).get("issues"):
                print("  critic issues: " + "; ".join(report["critic"]["issues"])[:400])
    finally:
        if app is not None:
            await app.deps.agents.aclose()
        await client.close()
        await truth.close()
        await asyncio.to_thread(sync_client.close)


def main() -> None:
    """Entry point for ``uv run smoke``."""
    parser = argparse.ArgumentParser(prog="smoke")
    parser.add_argument("--scenario", action="append", help="scenario type, e.g. mule.classic (repeatable)")
    parser.add_argument("--decision", default="approve")
    parser.add_argument("--mode", choices=[m.value for m in LlmMode], default=None, help="override LLM_MODE")
    args = parser.parse_args()
    configure_logging("WARNING")
    asyncio.run(run(tuple(args.scenario or EXAMPLES), args.decision, args.mode))

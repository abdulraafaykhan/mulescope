"""Eval harness: runs the planted alerts through the graph and scores them.

For each ground-truth account it starts a graph run on the account's case,
auto-approves at the analyst gate, then compares the policy disposition with
the expected one and checks the stored report (citations, claim coverage,
tipping-off, injection). Each per-case result is saved as soon as it is
known, so a live run that hits a quota can be resumed with ``--resume`` and
skips cases already evaluated. Called by ``evals/cli.py``.
"""

from __future__ import annotations

import time
from typing import Any

from backend.app.agents.text import looks_like_instruction
from backend.app.core.wiring import AppObjects
from evals import metrics

AUTO_DECISION = {"decision": "approve", "user_id": "eval-harness", "role": "analyst"}


class EvalHarness:
    """Runs and scores planted alerts for one eval run."""

    def __init__(self, app: AppObjects, db: Any, truth: list[dict[str, Any]]) -> None:
        self._app, self._db, self._truth = app, db, truth

    async def open_run(self, mode: str, resume: str | None, graph_version: str) -> tuple[str, set[str]]:
        """Create a new eval run or reopen one; returns ``(run_id, done_case_ids)``."""
        evals = self._app.evals
        if resume:
            run = await evals.get_run(resume) if resume != "latest" else await evals.latest_unfinished(mode)
            if run is not None:
                await evals.update_run(run["id"], {"status": "running"})
                return run["id"], await evals.done_case_ids(run["id"])
        now = self._app.deps.clock.now()
        run_id = (await self._app.deps.counters.next_ids("eval_runs", "EVAL-", 1, now, width=4))[0]
        meta = await self._db["dataset_meta"].find_one(sort=[("created_at", -1)]) or {}
        await evals.create_run({
            "_id": run_id, "mode": mode, "status": "running", "dataset_seed": meta.get("seed"),
            "policy_version": self._app.deps.scoring.policy_version, "graph_version": graph_version,
            "started_at": now, "ended_at": None, "metrics": None, "created_at": now,
        })
        return run_id, set()

    async def evaluate(self, run_id: str, done: set[str], on_result: Any) -> list[dict[str, Any]]:
        """Evaluate every truth record not in ``done``; returns all results of the run."""
        cases = {c["account_id"]: c async for c in self._db["cases"].find({}, {"account_id": 1})}
        for gt in self._truth:
            case = cases.get(gt["account_id"])
            if case is None:
                result = self._base(run_id, gt, None) | {"error": "no alert/case for this account"}
            elif case["_id"] in done:
                continue
            else:
                result = await self._one(run_id, gt, case["_id"])
            await self._app.evals.save_result(result)
            on_result(result)
        return await self._app.evals.results(run_id)

    async def close_run(self, run_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Store the run metrics; the run stays resumable if any case errored."""
        m = metrics.summarise(results, len(self._truth))
        status = "completed" if m["errors"] == 0 and m["evaluated"] == len(self._truth) else "running"
        await self._app.evals.update_run(run_id, {"metrics": m, "status": status, "ended_at": self._app.deps.clock.now()})
        return m | {"status": status}

    # --- internals --------------------------------------------------------------

    def _base(self, run_id: str, gt: dict[str, Any], case_id: str | None) -> dict[str, Any]:
        return {
            "_id": f"{run_id}:{case_id or gt['account_id']}", "run_id": run_id, "case_id": case_id, "account_id": gt["account_id"],
            "scenario_type": gt["scenario_type"], "label": gt["label"], "expected": gt["expected_disposition"],
            "predicted": None, "correct": False, "score": None, "citations": 0, "invalid_citations": 0, "claim_coverage": 0.0,
            "tipping_off": False, "injection_obeyed": False, "agent_nodes": 0, "fallback_nodes": 0, "latency_ms": 0, "tokens": 0,
            "case_run_id": None, "error": None, "created_at": self._app.deps.clock.now(),
        }

    async def _start(self, case_id: str) -> str:
        """Start a fresh run; a reused run left 'running' by a dead process is failed first."""
        runner, runs = self._app.runner, self._app.deps.runs
        run = await runner.start_run(case_id)
        if run.get("status") == "running" and not runner.is_driving(run["id"]):
            await runs.update(run["id"], {"status": "failed", "error": "stale run found by eval harness"}, self._app.deps.clock.now())
            run = await runner.start_run(case_id)
        return str(run["id"])

    async def _one(self, run_id: str, gt: dict[str, Any], case_id: str) -> dict[str, Any]:
        app, deps = self._app, self._app.deps
        result = self._base(run_id, gt, case_id)
        t0 = time.perf_counter()
        try:
            case_run = await self._start(case_id)
            await app.runner.wait(case_run)
            if ((await deps.runs.get(case_run)) or {}).get("status") == "awaiting_decision":
                await app.runner.decide(case_id, dict(AUTO_DECISION))
                await app.runner.wait(case_run)
            run = await deps.runs.get(case_run) or {}
            if run.get("status") != "completed":
                return result | {"case_run_id": case_run, "error": f"run ended {run.get('status')}: {run.get('error', '')}"[:300]}
            case = await deps.cases.get(case_id) or {}
            evidence = {e["id"] for e in await deps.evidence.for_run(case_id, case_run)}
            report = await deps.reports.latest(case_id) or {}
            execs = await deps.node_execs.for_run(case_run)
            cited, invalid, coverage = metrics.citation_stats(report, evidence)
            remarks = [r["remarks"] or "" for r in await self._window_rows(case)] if gt["scenario_type"] == metrics.INJECTION_SCENARIO else []
            predicted = case.get("recommended_disposition")
            agent_execs = [e for e in execs if e.get("agent") != "code"]
            return result | {
                "case_run_id": case_run, "predicted": predicted, "correct": predicted == gt["expected_disposition"], "score": case.get("score"),
                "citations": cited, "invalid_citations": invalid, "claim_coverage": round(coverage, 4),
                "tipping_off": metrics.tipping_off(report, deps.playbook.tipping_off_terms),
                "injection_obeyed": metrics.injection_obeyed(gt["scenario_type"], predicted, gt["expected_disposition"], report, [r for r in remarks if looks_like_instruction(r)]),
                "agent_nodes": len(agent_execs), "fallback_nodes": sum(1 for e in agent_execs if e.get("fallback_used")),
                "latency_ms": int((time.perf_counter() - t0) * 1000), "tokens": int((run.get("totals") or {}).get("tokens", 0)),
            }
        except Exception as exc:  # one failing case must not stop the eval run
            return result | {"error": f"{type(exc).__name__}: {exc}"[:300], "latency_ms": int((time.perf_counter() - t0) * 1000)}

    async def _window_rows(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        alert = await self._app.alerts.get(case["alert_id"]) or {}
        window = alert.get("window") or {}
        if not window:
            return []
        return list(await self._app.deps.tx.ledger(case["account_id"], window["start"], window["end"]))

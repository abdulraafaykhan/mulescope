# Implementation Plan

Verification uses commands only. No new test files, no pytest or property-test tasks, and `uv run seed` is never run. Each logical fix is one commit with a short, plain message. All tasks run in one go, with no pauses or checkpoints between them.

- [x] 1. Capture the baseline and confirm the root causes (no edits)
  - Run `uv run smoke --mode fallback` and save the output as the baseline (dispositions, score, evidence count, action count, audit chain validity)
  - Run `uv run check-policy` and save the output as the baseline
  - Read-only checks on the stored data for CASE-0004 and CASE-0012: action `evidence_ids` and `run_id` belong to the first run and are not in the latest run's ledger
  - Read a stored `metric:inflow_total` evidence document and confirm the key that holds the value (the design expects `value`)
  - Do not commit anything in this task
  - _Bug_Condition: isBugCondition(X) from design (stale, zeroAmt)_
  - _Requirements: 1.4, 1.6, 3.1, 3.9_

- [x] 2. Route the narrative to Groq with a fallback model
  - Add `fallback_model: str | None = Field(default=None, min_length=1)` to `AgentModelConfig` in `backend/app/core/config_files.py`
  - In `config/llm.yaml` set `narrative_writer` to `provider: groq`, `model: "openai/gpt-oss-120b"`, `fallback_model: "openai/gpt-oss-20b"`, with a comment on how to switch back to Gemini
  - In `LlmClient.structured` (`backend/app/llm/client.py`) try the primary model, then `fallback_model`, then raise `LLMUnavailable`. Keep the cache key on the primary model and record the answering model in `meta.model` and `llm_cache.model`
  - Prefix every error string with `provider/model`
  - Profiler, Flow Analyst and Critic keep one model and the same config shape
  - Run `uv run smoke --mode fallback` and `uv run check-policy`, and compare with the baseline
  - Commit: "route narrative to groq"
  - _Bug_Condition: isBugCondition(X) where routing_
  - _Expected_Behavior: Property 2 (routed models) from design_
  - _Preservation: 3.1, 3.2, 3.3 from design_
  - _Requirements: 1.1, 2.1, 3.1, 3.2, 3.3_

- [x] 3. Cap LLM call time per node
  - In `LimitsConfig` and `config/llm.yaml` replace `timeout_seconds` and `max_retries` with `call_timeout_seconds: 20`, `max_attempts: 2`, `node_budget_seconds: 40`, and lower `backoff_max_seconds` to 5. Change the model and the YAML together because the model is `extra="forbid"`
  - In `llm/factory.py` pass `call_timeout_seconds` to httpx as a safety net
  - In `LlmClient._call` wrap `provider.complete` in `asyncio.timeout(call_timeout_seconds)`, take the semaphore first, loop `range(max_attempts)`, cap the backoff, and move to the next model when `retry_after` is too long or on a timeout
  - In `LlmClient.structured` wrap the body in `asyncio.timeout(node_budget_seconds)` and turn `TimeoutError` into `LLMUnavailable` with the errors so far
  - Run `uv run smoke --mode fallback` and `uv run check-policy`, and compare with the baseline
  - Commit: "cap llm call time per node"
  - _Bug_Condition: isBugCondition(X) where unbounded_
  - _Expected_Behavior: Property 2 (20 s call, 2 attempts, 40 s node) from design_
  - _Preservation: 3.3, 3.4 from design_
  - _Requirements: 1.2, 2.2, 3.3, 3.4_

- [x] 4. Log fallback reasons and show them in smoke output and the UI
  - Add `fallback_reason(exc)` to `backend/app/agents/text.py` (joins `detail["errors"]`, falls back to `message`, trims to 300 characters). Make `LLMUnavailable` carry `detail={"errors": meta.errors}` in the client
  - Set `meta["fallback_reason"]` in `_fallback` (`live_investigators.py`) and in the narrative and critic `except` blocks (`live_writers.py`)
  - In `graph/instrument.py` write `fallback_reason` (null by default) to `node_executions`, add it to the audit payload only when set, and add it to the SSE node event
  - In `evals/smoke.py` print the model and the reason on the agents line, and add a fallback node count to the run line
  - Add `fallback_reason?: string | null` to `NodeExecution` in `frontend/src/types/api.ts`. Show it in `DiagnosticsView.tsx` (banner list and row `title`) and `AgentsPanel.tsx` (Details warning line and `StreamState` rows)
  - Run `npm run build` in `frontend/`, then `uv run smoke --mode fallback` and compare with the baseline
  - Commit: "log fallback reasons"
  - _Bug_Condition: isBugCondition(X) where hidden_
  - _Expected_Behavior: Property 2 (visible fallback_reason) from design_
  - _Preservation: 3.4, 3.5 from design_
  - _Requirements: 1.3, 2.3, 3.4, 3.5_

- [x] 5. Refresh actions evidence on rerun and strip unknown ids
  - Add `refresh_proposed(idempotency_key, run_id, evidence_ids, now) -> bool` to the `ActionRepository` interface and to `MongoActionRepository` (one `update_one` filtered on `status: "proposed"`, sets `run_id`, `evidence_ids`, `updated_at`)
  - In `_persist_actions` (`graph/nodes/decide.py`) call it when `upsert_proposed` returns False, then limit the returned rows' `evidence_ids` to the current ledger, falling back to `signal_ids`
  - Add `strip_unknown_ids(text, valid)` to `agents/text.py`. Apply it in `TemplateNarrativeWriter.run`, in `_render` for `s.text`, and in `LiveNarrativeWriter._assemble` before the citations are computed
  - Approved, executed, rejected and cancelled actions keep their history. No run id in the key, so there is still one action per key
  - Run `uv run smoke --mode fallback` twice on the same case: the action count does not grow and every id in the report is in the latest ledger. Then run `uv run check-policy`
  - Commit: "refresh actions evidence on rerun"
  - _Bug_Condition: isBugCondition(X) where stale or inText_
  - _Expected_Behavior: Property 1 (current ledger ids only) from design_
  - _Preservation: 3.6, 3.7 from design_
  - _Requirements: 1.4, 1.5, 2.4, 2.5, 3.6, 3.7_

- [x] 6. Fix zero amounts in the template narrative
  - In `backend/app/agents/narrative.py` build `m` with `k.removeprefix("metric:")` so `m.get('inflow_total')` and `m.get('outflow_total')` find their values (use the value key confirmed in task 1)
  - Run `uv run smoke --mode fallback`. The narrative now shows the real totals, and dispositions, score and action counts match the baseline. Then run `uv run check-policy`
  - Commit: "fix zero amounts in template narrative"
  - _Bug_Condition: isBugCondition(X) where zeroAmt_
  - _Expected_Behavior: Property 1 (summary and STR amounts equal the metric evidence) from design_
  - _Preservation: 3.1, 3.8 from design_
  - _Requirements: 1.6, 2.6, 3.1, 3.8_

- [x] 7. Update PROGRESS.md and the README LLM model line
  - Add the decisions to `PROGRESS.md`: Groq `openai/gpt-oss-120b` with fallback `openai/gpt-oss-20b` for the narrative, the 20 s call, 2 attempt and 40 s node limits, `fallback_reason`, refresh instead of run id in the idempotency key (and why), and `strip_unknown_ids`
  - Add the known gaps to `PROGRESS.md`, including that an action cancelled or rejected in an earlier run still blocks a new proposal for the same key
  - Update the LLM model line in `README.md` to match `config/llm.yaml`
  - Commit: "update progress notes and readme model line"
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 8. Final verification: live smoke runs, fix what fails, then report
  - Never run `uv run seed`. Run straight through all sub-tasks with no pauses
  - _Expected_Behavior: Properties 1, 2 and 3 from design_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.9_

  - [x] 8.1 Re-run the fallback checks
    - Run `uv run smoke --mode fallback`, `uv run check-policy` and `npm run build` in `frontend/`, and compare with the baseline from task 1
    - _Requirements: 3.1, 3.9_

  - [x] 8.2 Run live smoke for both scenarios
    - Run `uv run smoke --mode live` for mule.classic and seller.shop and keep the full output
    - Pass means each run takes under 90 s, reports critic=pass and has no fallback nodes
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 8.3 Fix live failures (up to 2 fix attempts)
    - Skip this sub-task if both runs in 8.2 pass
    - For each failing run (critic=revise, a fallback node, or over 90 s), read the logged `fallback_reason` and the critic issues, find the cause and fix it
    - Known suspect: the critic fell back once earlier with no visible reason; `openai/gpt-oss-20b` structured output may be the cause. Check these causes:
      - Groq `json_object` response mode not returning valid JSON for the schema
      - `max_completion_tokens` too low for gpt-oss reasoning tokens, which shows as empty content or `finish_reason: "length"`
      - Schema mismatches between the model output and the Pydantic structured output model
    - Keep model names, token limits and modes in `config/llm.yaml`, not in code
    - After each fix attempt, re-run `uv run smoke --mode fallback`, `uv run check-policy` and the failing `uv run smoke --mode live` scenario
    - Each fix attempt is its own small commit with a short, plain message (for example "raise critic max completion tokens")
    - Stop after 2 fix attempts
    - _Bug_Condition: live run with critic=revise, a fallback node, or duration over 90 s_
    - _Expected_Behavior: Property 2 (routed models, bounded time, visible fallback_reason) from design_
    - _Preservation: 3.1, 3.3, 3.4 from design_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.3, 3.4_

  - [x] 8.4 Check the live rerun path on mule.classic
    - Run `uv run smoke --mode live` for mule.classic a second time on the same case
    - Pass means: no duplicate actions for the case (idempotency keys are unique), every EVD id cited in the new report is in the new run's ledger, and critic=pass
    - Check this with the smoke output or a read-only throwaway `uv run python -c` query. Do not save test files
    - If it fails, treat it like 8.3 and count the fix toward the 2-attempt limit
    - _Expected_Behavior: Property 1 (current ledger ids only) from design_
    - _Preservation: 3.6, 3.7 from design_
    - _Requirements: 2.4, 2.5, 3.6, 3.7_

  - [x] 8.5 Report the results
    - Show the full live smoke output for both scenarios and the rerun
    - List each fix attempt with its cause and commit message
    - Only after the fix attempts, list what still fails, with the `fallback_reason` text, the critic issues and any unknown ids or amounts involved
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

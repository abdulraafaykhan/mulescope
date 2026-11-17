# Bugfix Requirements Document

## Introduction

The first live runs (`LLM_MODE=live`) of MuleScope show five related defects. Gemini is unreachable from this machine, so the narrative writer always falls back. Calls wait too long (60 s timeout, 3 retries, 30 s backoff, no per-node budget), so a run takes about five minutes. A fallback gives no visible reason. Live reports end with critic=revise. Both reports say the account "received ₹0 and sent ₹0".

Investigation of the code and the Atlas data (read-only, CASE-0004 and CASE-0012) found these root causes:

- **Stale evidence ids (defect 4).** Action idempotency keys are `case_id:type:target`, with no run id. `MongoActionRepository.upsert_proposed` skips an existing key. `_persist_actions` in `graph/nodes/decide.py` then returns the old action rows, whose `evidence_ids` and `run_id` belong to the first run. CASE-0004 has RUN-00001 (EVD-000001 to 000031, fallback) and RUN-00003 (EVD-000061 to 000093, live). The RUN-00003 report (RPT-00003) cites EVD-000026 to 000030 in the action lines. Those ids come from RUN-00001's actions. The ledger, the critic input and `evidence_for_run` are not stale. Evidence ids are not renumbered after the flow analyst, and the `llm_cache` key includes the full user prompt, so the cache is not the cause. `_render` in `live_writers.py` also filters only `evidence_ids`, not `EVD-` ids written inside a sentence's text.
- **₹0 amounts (defect 5).** `TemplateNarrativeWriter` builds `m` with keys like `metric:inflow_total` but reads `m.get('inflow_total')`, so it always gets 0. The flow tools, `by_senders`, `to_float` and `party_key` are correct: the stored evidence shows ₹6,21,132 in, ₹6,31,117 out, and top receivers with real amounts.
- **Timeouts (defect 2).** `httpx.AsyncClient(timeout=...)` limits each phase, not the whole request. `_call` retries up to `max_retries` times and `structured` adds a repair attempt, so one node can use many calls. Nothing bounds a node.
- **Hidden reasons (defect 3).** `LlmClient` gathers `meta.errors`, but `LLMUnavailable` is raised without them. The `_fallback` helpers and `LiveCritic` keep only the exception class name. `instrument.py` has no `fallback_reason` field.
- **Provider routing (defect 1).** `AgentModelConfig` holds one provider and one model, with no fallback model, and `config/llm.yaml` sends `narrative_writer` to Gemini.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `narrative_writer` is configured as `gemini` / `gemini-3.8-flash` and Gemini is unreachable (`gemini-3.8-flash` and `gemini-3.7-flash` time out after 20 s, `gemini-3.6-flash` returns 503) THEN the system always falls back to the template narrative, because `AgentModelConfig` has a single provider and model and no fallback model.

1.2 WHEN an agent call has an LLM error, or a node makes several calls (retries, repair attempt, a critic-revise loop) THEN the system lets one node run for minutes, because the HTTP timeout is 60 s per phase, `max_retries` is 3, backoff goes up to 30 s, and there is no per-node budget. A live run takes about five minutes.

1.3 WHEN a node falls back (HTTP status, timeout, or invalid JSON after repair) THEN the system records only "fallback (LLMUnavailable)", because `LLMUnavailable` is raised without `meta.errors`. `node_executions` has no `fallback_reason`, and the smoke output, `DiagnosticsView` and `AgentsPanel` cannot show why. The critic fell back once in the seller run with no visible reason.

1.4 WHEN a case is run again and the planner proposes actions whose `idempotency_key` already exists from an earlier run (key = `case_id:type:target`) THEN the system returns the old action rows, with the earlier run's `evidence_ids` and `run_id`. The narrative cites those ids in the action lines, so the report cites ids that are not in the current run's ledger, for example EVD-000026 to 000030 in RPT-00003 (CASE-0004) and EVD-000057 in CASE-0012. The critic reports "cites unknown evidence ids" and the run ends with critic=revise.

1.5 WHEN the live narrative writer keeps a sentence whose text contains an `EVD-` id that is not in the ledger THEN the system keeps the id, because `_render` checks only the `evidence_ids` list and not ids inside the text.

1.6 WHEN the narrative is built from the evidence ledger THEN the system writes "received ₹0 and sent ₹0" in the executive summary and "Total credits ₹0; total debits ₹0" in the STR narrative. `TemplateNarrativeWriter` reads `m.get('inflow_total')` from a dict keyed `metric:inflow_total`, so the amounts are always 0. The live critic then flags these lines as unsupported claims.

### Expected Behavior (Correct)

2.1 WHEN an agent is routed in `config/llm.yaml` THEN the system SHALL support a `provider`, a primary `model` and an optional `fallback_model` per agent, with `groq` and `gemini` both selectable. `narrative_writer` SHALL use Groq with `openai/gpt-oss-120b` as primary and `openai/gpt-oss-20b` as fallback model. Switching an agent back to Gemini SHALL need only a config change. The system SHALL try the fallback model before the template, and SHALL record the model that answered.

2.2 WHEN an LLM call or node runs THEN the system SHALL apply a total per-call timeout of 20 s (a wall-clock limit, not a per-phase limit) and at most 2 attempts per call. It SHALL apply a 40 s budget per node that covers all attempts, the fallback model and the repair attempt. When the budget is spent, the node SHALL fall back to its template at once. All values SHALL come from `config/llm.yaml`. A live run SHALL finish in about one minute.

2.3 WHEN a node falls back THEN the system SHALL keep the reason (HTTP status, timeout, or invalid JSON, with the provider and model) from `meta.errors` and carry it through `LLMUnavailable`. It SHALL store it as `fallback_reason` in the `node_executions` record, print it in the `uv run smoke` output, and show it in `DiagnosticsView` and `AgentsPanel`, with `NodeExecution` in `frontend/src/types/api.ts` updated.

2.4 WHEN actions are planned for a run THEN the system SHALL make sure every id in the report, the actions and the critic input exists in the current run's evidence ledger. An action that already exists for the same idempotency key SHALL be reused without duplication, but its `evidence_ids` (and `run_id`) SHALL be refreshed to the current run while it is still `proposed`. An action that was already approved or executed SHALL keep its history, and the narrative SHALL cite only ids in the current ledger. A live run SHALL end with critic=pass.

2.5 WHEN the live narrative writer renders a sentence THEN the system SHALL remove or reject any `EVD-` id in the sentence text that is not in the ledger, as well as any in `evidence_ids`.

2.6 WHEN the narrative reports totals THEN the system SHALL read the metric values from the correct evidence keys, so the summary and the STR narrative show the real credit and debit totals (for example ₹6,21,132 and ₹6,31,117 for CASE-0004), identical to the metric evidence.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `LLM_MODE=fallback`, or live mode runs with no key THEN the system SHALL CONTINUE TO run the whole graph with template agents and no network calls, and `uv run smoke` in fallback mode SHALL CONTINUE TO end with mule.classic as STR draft and seller.shop as Close.

3.2 WHEN the Profiler, Flow Analyst or Critic are routed to Groq with a single model THEN the system SHALL CONTINUE TO work with the existing config shape (`fallback_model` is optional) and the same prompts and structured output.

3.3 WHEN a call succeeds on the first attempt within the limits THEN the system SHALL CONTINUE TO cache the validated response in `llm_cache` (key from model, prompt version, system and user text), return cache hits at no cost, and keep the semaphore of `max_concurrency` concurrent calls.

3.4 WHEN any LLM call fails for any reason THEN the system SHALL CONTINUE TO use the node's template output, never fail the case, and never change the deterministic metrics, score or disposition.

3.5 WHEN a node completes without a fallback THEN the system SHALL CONTINUE TO write the same `node_executions` fields and audit records, with no `fallback_reason`, and the UI SHALL CONTINUE TO show it as done.

3.6 WHEN actions are proposed for a case with no earlier run, or the analyst approves, edits, overrides or rejects THEN the system SHALL CONTINUE TO create one action per idempotency key, keep the maker-checker rules and the mock executor, and keep the audit hash chain valid.

3.7 WHEN a narrative sentence has only valid ids, or a sentence has no citation THEN the system SHALL CONTINUE TO keep valid sentences and drop uncited ones, take the risk score, typologies, disposition line and actions from the template, and replace a customer letter with a tipping-off term by the neutral template.

3.8 WHEN counterparty, flow path, sender overlap and complaint tools are called THEN the system SHALL CONTINUE TO return the same read-only results, and the flow analyst facts SHALL CONTINUE TO show the same amounts.

3.9 WHEN the seed data is used THEN the system SHALL CONTINUE TO leave the active dataset (seed 42), cases, runs and audit logs untouched. This work SHALL NOT run `uv run seed` and SHALL add no new test files. It is checked with `uv run smoke --mode live` for mule.classic and seller.shop, where each run finishes in under 90 s with critic=pass and no fallback badges. Anything that still fails SHALL be listed.

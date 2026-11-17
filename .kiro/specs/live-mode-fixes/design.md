# Live Mode Fixes Bugfix Design

## Overview

The first live runs (`LLM_MODE=live`) show five linked defects: the narrative writer is routed to an unreachable provider with no fallback model (1.1), nothing bounds how long a node can run (1.2), a template fallback gives no visible reason (1.3), re-running a case reuses old action rows whose evidence ids are not in the current ledger (1.4, 1.5), and the template narrative prints "₹0" for credits and debits (1.6).

The fix is small and targeted:

- **Routing (1):** add an optional `fallback_model` to each agent in `config/llm.yaml`. `LlmClient.structured` tries the primary model, then the fallback model, then raises `LLMUnavailable`. `narrative_writer` moves to Groq `openai/gpt-oss-120b` with fallback `openai/gpt-oss-20b`.
- **Time limits (2):** a wall-clock limit of 20 s per call, at most 2 attempts per call, and a 40 s budget for one structured call. Each node makes exactly one structured call (all attempts, the fallback model and the repair), so this is the per-node budget. All values are in `config/llm.yaml`.
- **Visible reasons (3):** `LLMUnavailable` carries the error list. A single helper turns it into `fallback_reason`, which `instrument.py` stores in `node_executions` and the smoke output, `DiagnosticsView` and `AgentsPanel` show.
- **Stale ids (4, 5):** keep the idempotency key `case_id:type:target` and refresh `evidence_ids` and `run_id` on an existing action that is still `proposed`. Add a sanitizer that strips any `EVD-` id not in the current ledger from the template text and the LLM text before the critic runs.
- **₹0 (6):** strip the `metric:` prefix when the template reads the metric values.

**Choice for defect 4: refresh, not "run id in the key".** Putting the run in the key would create a second `proposed` action for every earlier run. `execute_actions` runs every `proposed` or `approved` action of the case (`deps.actions.for_case`), so the analyst would execute the same hold twice. `ActionsPanel` lists every action of the case with no run filter, so it would show duplicates and offer Approve on stale ones. We would also need to cancel the superseded ones. Refreshing needs one new repository method and keeps one action per key, as rule 3.6 requires. Actions that are already approved, executed, rejected or cancelled keep their history and their original ids.

## Glossary

- **Bug_Condition (C)**: Input where a live run, a re-run or a template narrative gives one of the defective results above.
- **Property (P)**: The corrected behaviour for those inputs (see Correctness Properties).
- **Preservation**: Fallback mode, single-model Groq routes, cache hits, deterministic metrics, score and disposition, maker-checker rules and the audit chain, which must not change.
- **Ledger**: The set of evidence ids written for the current `run_id` (`state["evidence"]`).
- **Call**: One request to one model at one provider (one `provider.complete`).
- **Structured call**: One `LlmClient.structured(...)`: cache lookup, primary model, fallback model, repair. One per node, so it is the unit of the 40 s node budget.
- **fallback_model**: Optional second model of the same provider for one agent.
- **fallback_reason**: Short text saying why a node used its template (HTTP status, timeout or invalid JSON, with provider and model). `None` when no template fallback happened.
- **`_persist_actions`** (`backend/app/graph/nodes/decide.py`): Plans actions, inserts the new ones and returns the rows for the planned keys.
- **`upsert_proposed`** (`MongoActionRepository`): Inserts an action unless its `idempotency_key` exists.

## Bug Details

### Bug Condition

The bug shows up when a live narrative, a re-run, a slow provider or a template narrative is involved. The code either has one model and no budget (1, 2), drops the error list (3), returns old rows with the first run's ids (4, 5), or reads the wrong dictionary key (6).

**Formal Specification:**
```
FUNCTION isBugCondition(X)
  INPUT: X of type CaseRunInput { mode, agentRoute, providerState, priorRuns, narrativeSource }
  OUTPUT: boolean

  routing   := X.mode = "live" AND X.agentRoute.fallback_model = NONE
               AND X.agentRoute.provider unreachable
  unbounded := X.mode = "live" AND nodeWallClock(X) > 40s
               OR callWallClock(X) > 20s OR attemptsPerCall(X) > 2
  hidden    := X.nodeUsedTemplate AND X.mode = "live" AND fallbackReasonVisible(X) = false
  stale     := X.priorRuns NOT EMPTY
               AND EXISTS a IN plannedActions(X) :
                     a.idempotencyKey IN existingKeys(X.priorRuns)
                     AND a.status = "proposed"
                     AND a.evidence_ids NOT SUBSET OF ledger(X.currentRun)
  inText    := EXISTS id IN evdIdsInNarrativeText(X) : id NOT IN ledger(X.currentRun)
  zeroAmt   := X.narrativeSource = "template"
               AND metricEvidence(X).inflow_total > 0
               AND narrativeShowsInflow(X) = 0

  RETURN routing OR unbounded OR hidden OR stale OR inText OR zeroAmt
END FUNCTION
```

### Examples

- **Stale ids (1.4):** CASE-0004 has RUN-00001 (EVD-000001..31, fallback) and RUN-00003 (EVD-000061..93). RPT-00003 cites EVD-000026..30 in the action lines. Expected: only ids from EVD-000061..93. Critic: "cites unknown evidence ids", verdict revise.
- **Same for CASE-0012:** the report cites EVD-000057, which is not in the RUN ledger.
- **₹0 (1.6):** CASE-0004 evidence has ₹6,21,132 in and ₹6,31,117 out. The summary says "received ₹0 and sent ₹0". Expected: the real totals.
- **Hidden reason (1.3):** the critic falls back in the seller run. The record says "fallback (LLMUnavailable)". Expected: for example "groq/openai/gpt-oss-20b: HTTP 503; groq/openai/gpt-oss-20b: invalid output after repair".
- **Timeout (1.2):** Gemini times out at 60 s per phase and retries 3 times with up to 30 s backoff, so one node runs for minutes. Expected: template after at most 40 s.
- **Edge case:** a re-run finds an action that was already `executed`. Expected: it keeps its history, the narrative cites current ledger ids for it, and no new action is created.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `LLM_MODE=fallback` and live mode with no key run the whole graph with template agents and no network calls. `uv run smoke` ends with mule.classic as STR draft and seller.shop as Close (3.1).
- Profiler, Flow Analyst and Critic on Groq with one model work with the same config shape, the same prompts and the same structured output (3.2).
- A first-attempt success is cached in `llm_cache` with the key from model, prompt version, system and user. Cache hits stay free. The semaphore of `max_concurrency` stays (3.3).
- Any LLM failure still gives the node's template output, never a failed case, and never changes metrics, score or disposition (3.4).
- A node with no fallback writes the same `node_executions` fields and audit records, plus `fallback_reason: null` (3.5).
- One action per idempotency key, maker-checker rules, mock executor and audit hash chain (3.6).
- Valid sentences kept, uncited sentences dropped, risk score, typologies, disposition line and actions from the template, tipping-off letter replaced (3.7).
- Read-only tool results and flow analyst amounts (3.8).
- Seed data (3.9). No `uv run seed`, no new test files.

**Scope:**
Everything that is not a live provider failure, a re-run with existing action keys, an `EVD-` id outside the ledger, or the template amounts is unaffected. In fallback mode the only visible change is that the narrative shows the real amounts instead of ₹0.

## Hypothesized Root Cause

The causes were confirmed by reading the code and the stored data in the requirements phase:

1. **Routing (1.1):** `AgentModelConfig` has one `provider` and one `model`. `LlmClient.structured` has nothing to try after the primary model.
2. **No wall-clock limit (1.2):** `httpx.AsyncClient(timeout=60)` limits each phase (connect, write, read), not the request. `_call` retries `max_retries=3` with backoff up to 30 s. `structured` adds a repair attempt that repeats the whole retry loop. No limit spans the node.
3. **Dropped errors (1.3):** `_call` appends to `meta.errors`, but `structured` raises `LLMUnavailable("output did not match…")` or `LLMUnavailable(f"{provider.name} failed…")` and the callers keep `type(exc).__name__`. `instrument.py` has no field for a reason.
4. **Idempotency without run (1.4):** `upsert_proposed` returns False for an existing key and does nothing. `_persist_actions` then reads `for_case` and returns the rows of the first run with their `evidence_ids`. The narrative cites them in the action lines (`a.get('evidence_ids')`).
5. **Partial filter (1.5):** `_render` checks `s.evidence_ids` but not `EVD-` ids written in `s.text`.
6. **Wrong key (1.6):** `m = {k: ... for k in by_key if k.startswith("metric:")}` keeps the `metric:` prefix, but the code reads `m.get('inflow_total')`.

## Correctness Properties

Property 1: Bug Condition - Narrative cites only the current ledger and shows real amounts

_For any_ run where the bug condition holds for stale ids, ids in text or ₹0 amounts (a re-run with existing action keys, a live sentence with an unknown `EVD-` id in its text, or a template narrative with metric evidence), the fixed narrative writer and `plan_actions` SHALL produce a report, actions and critic input whose every `EVD-` id is in the current run's ledger, whose action lines carry current-run ids, and whose summary and STR amounts equal the `metric:inflow_total` and `metric:outflow_total` evidence values.

**Validates: Requirements 2.4, 2.5, 2.6**

Property 2: Bug Condition - Bounded live calls, routed models and visible reasons

_For any_ live structured call, the fixed client SHALL use at most 2 attempts per call, end each call within 20 s and the whole structured call within 40 s, try `fallback_model` before the template when one is configured, record the model that answered, and on template fallback SHALL set `fallback_reason` (provider, model and cause) in the node meta, `node_executions`, the smoke output and the UI.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 3: Preservation - Fallback mode and unaffected paths

_For any_ input where the bug condition does NOT hold (fallback mode, single-model Groq routes, cache hits, first runs, analyst decisions, nodes with no fallback), the fixed code SHALL produce the same result as the original code, preserving template-only operation, cache keys and hits, one action per idempotency key, maker-checker rules, deterministic metrics, score and disposition, node_executions fields (plus a null `fallback_reason`) and the valid audit chain.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**

## Fix Implementation

### Changes Required

**1. Config: `config/llm.yaml` and `backend/app/core/config_files.py`**
- `AgentModelConfig`: add `fallback_model: str | None = Field(default=None, min_length=1)`. Same provider as the primary. Existing configs stay valid.
- `LimitsConfig`: replace `timeout_seconds` and `max_retries` with `call_timeout_seconds: 20`, `max_attempts: 2`, `node_budget_seconds: 40`. Lower `backoff_max_seconds` to 5. Keep `max_concurrency`, `backoff_base_seconds` and `repair_attempts`. The model is `extra="forbid"`, so the YAML and the model change together.
- `narrative_writer`: `provider: groq`, `model: "openai/gpt-oss-120b"`, `fallback_model: "openai/gpt-oss-20b"`. Add a comment that `provider: gemini` plus a Gemini model switches it back with no code change.
- `llm/factory.py`: pass `cfg.limits.call_timeout_seconds` as the httpx timeout. It is only a safety net, because the client enforces the wall-clock limit.
- `agents/suite.py`: `models[...]` stays the primary name. `build_live_suite` needs no change, since `client.has(provider)` already decides live or template.

**2. Client: `backend/app/llm/client.py`**
- `structured`: wrap the body in `async with asyncio.timeout(limits.node_budget_seconds)`. A `TimeoutError` becomes `LLMUnavailable` with the errors so far plus "node budget 40s spent".
- Build `models = [route.model, route.fallback_model]` (skip `None`). For each model run the existing repair loop. The cache key keeps `route.model` (primary), so a re-run hits the cache whichever model answered. `meta.model` records the answering model, and `llm_cache.model` stores it.
- `_call`: take the semaphore first (the wait counts toward the node budget only), then wrap `provider.complete` in `asyncio.timeout(limits.call_timeout_seconds)` so the 20 s limit starts when the request starts. On `TimeoutError`, append `"{provider}/{model}: timeout after 20s"` and stop retrying this model, because a second 20 s wait on a slow model rarely helps and would leave no time for the fallback model.
- `_call`: loop `range(max_attempts)`. For 429 or 5xx, wait `min(retry_after or delay, backoff_max_seconds)` and retry once. If `retry_after` is larger than `backoff_max_seconds` or the remaining budget, do not sleep and move to the next model.
- Every error string is prefixed with `provider/model`, for example `groq/openai/gpt-oss-120b: HTTP 503`.
- When a model has failed or its output was invalid after repair, go on with the next model. After the last, `raise LLMUnavailable("no model answered", detail={"errors": meta.errors})`. A repair attempt uses the model that produced the invalid output and counts toward the same budget.

**3. Fallback reason: `agents/text.py`, `live_investigators.py`, `live_writers.py`, `instrument.py`**
- New function `fallback_reason(exc: Exception) -> str` in `agents/text.py`: joins `exc.detail["errors"]` with "; ", falls back to `exc.message`, trims to 300 characters. It never contains keys or prompts (errors hold the first 200 characters of the response body, as today).
- `_fallback` (investigators), the narrative `except` and the critic `except` set `meta["fallback_reason"] = fallback_reason(exc)` and keep the existing summary text.
- `instrument.py`: add `"fallback_reason": None` to the initial insert, store `meta.get("fallback_reason")` on completion, add it to the audit payload only when set, and add `fallback_reason` to the SSE node event.
- Template-only runs (fallback mode) set no reason, so their records are unchanged apart from the null field.

**4. Stale ids: `repositories/`, `graph/nodes/decide.py`**
- `ActionRepository` interface and `MongoActionRepository`: add `refresh_proposed(idempotency_key, run_id, evidence_ids, now) -> bool`. One `update_one` with filter `{idempotency_key, status: "proposed"}` and `$set {run_id, evidence_ids, updated_at}`. It is atomic and never touches approved, executed, rejected or cancelled actions.
- `_persist_actions`: when `upsert_proposed` returns False, call `refresh_proposed(action.idempotency_key, state["run_id"], signal_ids, now)`. The same-run override path (`execute_actions` calls `_persist_actions` again) refreshes with the same ids, so it is harmless.
- `_persist_actions`: before returning, make the returned rows match the ledger. For each row, `evidence_ids = [i for i in row["evidence_ids"] if i in ledger_ids] or signal_ids` (covers older approved or executed actions). This only changes the copy sent to the narrative, not the stored history.
- `execute_actions` and `ActionsPanel` need no change: there is still one action per key, so nothing is run or shown twice.
- Not changed, noted for the final report: an action that was `cancelled` or `rejected` in an earlier run still blocks a new proposal for the same key. This is the current behaviour and is outside this bug.

**5. Defence in depth: `agents/text.py`, `narrative.py`, `live_writers.py`**
- New `strip_unknown_ids(text, valid) -> str` in `agents/text.py`: removes every `[EVD-nnnnnn]` and bare `EVD-nnnnnn` that is not in `valid`, then fixes doubled spaces.
- `TemplateNarrativeWriter.run`: apply it to `summary_md`, `str_md` and `customer_md` before computing `citations`.
- `_render` (live): apply it to `s.text` as well as filtering `evidence_ids`.
- `LiveNarrativeWriter._assemble`: apply it again to the final `summary_md`, `str_md` and `customer_md`, then compute `citations`. The narrative node runs before the critic, so the critic never sees an unknown id. If stripping leaves a claim without a citation, the critic still reports it, which is the correct outcome.

**6. ₹0: `agents/narrative.py`**
- `m = {k.removeprefix("metric:"): by_key[k]["data"].get("value") for k in by_key if k.startswith("metric:")}`. The implementer confirms the `value` key against a stored `metric:inflow_total` document (read-only) before editing.

**7. Smoke output and frontend**
- `evals/smoke.py`: the agents line prints the model and the reason, for example `critic=fallback[groq/openai/gpt-oss-20b: HTTP 503]` or `narrative_writer=llm[openai/gpt-oss-120b](5210 tok)`. Add a "fallback nodes" count to the run line.
- `frontend/src/types/api.ts`: add `fallback_reason?: string | null;` to `NodeExecution` (the file is edited by hand, like the neighbouring fields; if an OpenAPI generation step exists for it, run that instead).
- `DiagnosticsView.tsx`: the fallback banner lists each fallback node with its reason (`node: reason`), and each timeline row gets a `title` with the reason.
- `AgentsPanel.tsx`: `Details` shows a warning line "Fallback: {reason}" when `exec.fallback_reason` is set, and `StreamState` rows show it from the SSE event when the diagnostics row is not yet loaded.

## Testing Strategy

### Validation Approach

The brief forbids new test files and `uv run seed`. Validation therefore uses the existing commands, read-only queries against the stored data and throwaway one-off snippets run with `uv run python -c` that are not saved. The two-phase approach still applies: first show the bug on the unfixed code, then check the fix and preservation.

### Exploratory Bug Condition Checking

**Goal**: Confirm the root causes on the unfixed code before editing.

**Test Plan**: Read-only queries and one-off snippets. Record the output of `uv run smoke --mode fallback` first as the baseline.

**Test Cases**:
1. **Stale ids**: read `actions` and `evidence` for CASE-0004 and CASE-0012; the action `evidence_ids` belong to RUN-00001, not the latest run (will fail on unfixed code).
2. **₹0**: call `TemplateNarrativeWriter.run` with a ledger holding `metric:inflow_total` (data value 621132) and check the summary says ₹0 (will fail on unfixed code).
3. **Text ids**: call `_render` with a sentence whose text holds an unknown id and valid `evidence_ids`; the id stays (will fail on unfixed code).
4. **Hidden reason**: force `LLMUnavailable` with a fake provider and check the meta has no reason (will fail on unfixed code).
5. **Timeout**: a fake provider that sleeps for 60 s; the structured call takes longer than 40 s (will fail on unfixed code).

**Expected Counterexamples**:
- Action rows with `run_id` of an older run and ids outside the current ledger; `m.get('inflow_total')` returning None; a node lasting minutes.
- Possible causes if not confirmed: a cache hit returning an old report, or evidence renumbering. The requirements phase already excluded both.

### Fix Checking

**Goal**: For every input where the bug condition holds, the fixed code gives the expected behaviour.

**Pseudocode:**
```
FOR ALL X WHERE isBugCondition(X) DO
  result := runCase_fixed(X)
  ASSERT expectedBehavior(result)
END FOR

FUNCTION expectedBehavior(result)
  RETURN evdIds(result.report, result.actions, result.criticInput) SUBSET OF ledger(result.run)
     AND amountsShown(result.report) = metricEvidence(result.run)
     AND (result.nodeUsedTemplate IMPLIES result.fallbackReason NOT EMPTY)
     AND nodeWallClock(result) <= 40s AND callWallClock(result) <= 20s
     AND attemptsPerCall(result) <= 2
     AND (result.fallbackModelConfigured AND primaryFailed IMPLIES fallbackModelTried(result))
END FUNCTION
```

### Preservation Checking

**Goal**: For every input where the bug condition does NOT hold, the fixed code gives the same result as the original.

**Pseudocode:**
```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT original(X) = fixed(X)
END FOR
```

**Testing Approach**: Property-based testing is the right tool in general, but with no new test files the same coverage comes from running the existing evaluation commands over the seeded 40 alerts and comparing with the baseline. `uv run check-policy` is the property-style check for deterministic score and disposition.

**Test Plan**: Capture the baseline from the unfixed code, then repeat after the fix.

**Test Cases**:
1. **Fallback smoke**: `uv run smoke --mode fallback` gives the same dispositions (mule.classic STR draft, seller.shop Close), score, evidence count, actions and audit chain validity as the baseline; only the amounts in the narrative differ.
2. **Policy**: `uv run check-policy` gives the same result as the baseline.
3. **Single-model Groq routes**: profiler, flow_analyst and critic still run with no `fallback_model` and the same prompts.
4. **First-run actions**: a case with no earlier run creates one action per key with the same fields.

### Unit Tests

Throwaway snippets only (not saved):
- `strip_unknown_ids` keeps valid ids, removes unknown bracketed and bare ids, and leaves text without ids unchanged.
- `fallback_reason` with and without `detail["errors"]`, and the 300 character limit.
- Client with a fake provider: 503 then success (2 attempts), timeout then fallback model, both models invalid JSON (reason lists both), budget spent (template).
- `refresh_proposed` updates a `proposed` action and does nothing to an `executed` one.

### Property-Based Tests

Covered by existing commands, not new files:
- `uv run check-policy` over the seeded alerts (score and disposition unchanged).
- `uv run smoke --mode fallback` for both scenarios, repeated twice on the same case: the action count does not grow, and every id in the report is in the latest run's ledger.

### Integration Tests

- `uv run smoke --mode live` for mule.classic and seller.shop: each finishes in under 90 s, critic verdict `pass`, no fallback badges, the narrative cites only current-run ids and shows the real amounts. Anything that still fails is listed in the final report.
- Run the same live case twice: the second run refreshes the `proposed` actions (same ids, new `run_id`), creates no duplicates, and ends with critic=pass.
- `npm run build` in `frontend/` passes with the new `fallback_reason` field in `NodeExecution`, `DiagnosticsView` and `AgentsPanel`.
- Never run `uv run seed`.

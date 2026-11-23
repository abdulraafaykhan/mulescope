# Build Prompt: MuleScope Assurance Release (v2)

Nov 23, 2026 · @Abdul Raafay Khan

You are a senior full-stack engineer. MuleScope is a working MVP: a LangGraph-based AML triage copilot for mule-account and rapid pass-through alerts. Your job is to make it **defensible, hardened and demonstrable** without rewriting it. Read this whole document, then the files in section 2, then pick up workstreams from section 6.

The release is called **Assurance**: prove it works (evidence), protect it (controls), show it live (monitoring).

## 1. How to work

- The work is split into **12 independent workstreams (WS-A to WS-L)**. Each one has its own goal, files, tasks and "done when". Any workstream can be built on its own, in any order, and each one leaves the repo green. Recommended order, not required: A, B, C, D, E, F, G, H, I, J, L, K (K touches many files, so run it when nothing else is in flight).
- Where two workstreams share something, the shared piece is defined once in **section 4 (shared contracts)**. If it already exists when you start, use it. If not, create it exactly as specified there.
- **Verify** means: check the real code or service, note the result in `PROGRESS.md` under "Decisions", and adapt if reality differs. Do not guess.
- **Do not overbuild.** Implement what is written. No plugin frameworks, generic abstractions, extra caching layers or speculative options. Also do not cut corners: every item marked required must be complete, typed, tested and documented. Items marked **(optional)** can be skipped if time is short.
- Prefer many small, finished commits over one large one.

### Definition of done for every workstream

1. `ruff check`, `ruff format --check` and `mypy` (the strict scope in `pyproject.toml`) are clean for the files you touched.
2. New or changed behaviour has tests. Use unit tests by default. Use integration tests only when a real database is needed.
3. The core result is unchanged: `uv run check-policy` is still 40/40 with 0 mules closed (or `uv run gate`, if WS-A exists), unless the workstream states a policy change.
4. Every new setting is in `.env.example` (secrets empty). `tests/unit/test_no_secrets.py` stays green.
5. `PROGRESS.md` gets a short entry: what changed, decisions, known gaps.

### Stop and report to the user when

- A check stays red after two different fixes. Explain the root cause and propose another approach.
- The core results change and the workstream did not intend that.
- A step needs a destructive command on the main databases (for example `uv run seed --reset`). Ask first.
- You reach the pre-registration checkpoint in WS-D.

## 2. Starting state and verified facts

Read first, in this order: `docs/BUILD_PROMPT.md` (original spec), `PROGRESS.md`, `.kiro/steering/*.md` (tech, structure and product rules), then this file. This file wins for new work. The steering rules stay in force except for the changes in section 3.

What exists: FastAPI backend with layered services and repositories, a 14-node LangGraph case graph with a Mongo checkpointer and an analyst interrupt, four agents (template and live versions on Groq), an own LLM client (cache, semaphore of 2, retry, fallback model, schema repair), a hash-chained audit log, a `datagen` package with 40 planted accounts (seed 42, 300 customers) and a separate truth database, and a React analyst UI. Current results: `check-policy` 40/40, 0 mules closed.

Facts already verified in the code:

- `load_case` copies `alert.window` into the run. The window is fixed when the alert is created.
- `MetricsService` is built on ports (`LedgerPort`, `GetPort`, `ComplaintPort`). `compute_metrics` and the detector rules (`evaluate`, `WindowStats`) are pure functions.
- `ComplaintPort.for_beneficiary` has no time filter.
- `cli.generate` sets the background population to `customers - planted`, where `planted` counts every variant in the `scenarios:` YAML block.
- Transfer ids (`TRF...`) are ranked by time across all transfers, so adding transactions renumbers them. Accounts, amounts and balances are unaffected.
- Only credit remarks are wrapped in `<untrusted_data>`. KYC occupation and city (Profiler prompt), counterparty names inside tool results (Flow Analyst prompt) and the customer name (narrative prompt) are plain text.
- Evidence ids come from a global counter and appear in narrative and critic prompts, so a re-run misses `llm_cache`.
- `DecisionRequest` and `ActionPatch` take `user_id` and `role` from the request body. There is no authentication.
- The detector builds alert ids from `alerts.count()` and loads every window row into Python.
- `store_feedback` and `suppress_similar_alerts` are mocked and have no effect.
- There is no tracing integration in code. `langsmith` is in `uv.lock` only as a dependency of `langchain-core`.
- No Docker on the dev machine. MongoDB is Atlas M0 (512 MB). `tests/conftest.py` uses throwaway databases (`mst_`, `mstt_` prefixes) and refuses the production names.

## 3. Locked decisions and rule changes

| # | Decision |
| --- | --- |
| D1 | Prompts show per-run **evidence aliases** (`E1`, `E2`, ...). Code maps them back to real `EVD-` ids. Real ids are unchanged. |
| D2 | Closed cases are not re-alerted for `suppression_days` (config, default 30) unless the new window's inflow is at least `reopen_if_inflow_multiple` times the old trigger inflow (config, default 2.0). |
| D3 | Audit, run and case timestamps use the wall clock. Simulated time is only for data windows in staged mode. SLA KPIs are hidden in staged mode. |
| D4 | Rings are **linked cases** (`ring_id` and a ring view), not a new case type. Ring membership adds no score points. |
| D5 | Each truth record has an `expected_disposition` and `acceptable_dispositions`. Reports show plain accuracy and a **cost-weighted error**. |
| D6 | Auth: server-side session in MongoDB, httpOnly cookie, roles `analyst`, `senior_reviewer`, `auditor`, seeded demo users. No bypass flag. |
| D7 | Schema policy: always `--reset`, no migrations. Documented as a known limit. |
| D8 | New dependencies are allowed with exact pins, well-known and pure-Python where possible (Windows machine, no compiler). |
| D9 | Tests, CI and a gate command are required. This reverses the earlier "smoke commands only" instruction. |
| D10 | Metrics and targets are **pre-registered** before the first run on the test split. |
| D11 | Data packs are off by default. `uv run seed` with no pack flag produces exactly today's core dataset. |
| D12 | Seeds: core `42`, dev `1` to `5` (tuning allowed), test `100` to `199` (sealed), demo `900` (in no split). |
| D13 | Instant mode (today) stays the default. Staged mode is a second dataset mode. |
| D14 | An investigation uses the **latest evidence** (simulated now in staged mode, `alert.window` in instant mode). The window used is stored on the run and shown as "evidence as of". |
| D15 | A run found `running` at API startup is marked failed (`api_restart`) and can be re-run. It is not resumed. |
| D16 | Our own audit and diagnostics are the observability. LangSmith tracing is optional, off by default. |

Principles that apply everywhere:

1. **The core 40 are frozen.** Seed 42 with 300 customers and no packs keeps its accounts, amounts and balances.
2. **One kind of change per commit.** Never mix a policy or metric change with a data change.
3. **Tune on dev, report on test.** Only core and dev seeds may inform weights and thresholds. After you fix something against a pack, that pack is in-sample for those seeds.
4. **Honest numbers.** Failures on hard negatives and evasive mules are findings. Report them. Never weaken a test, widen a label or loosen a threshold to hide one.
5. **Synthetic only.** Network data uses reserved documentation ranges (IPv4 `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`; IPv6 `2001:db8::/32`).
6. **Nothing leaves the machine** except calls to the configured LLM provider.
7. **No invented regulatory facts.** Keep TODO verify notes for the STR deadline and structuring limits.
8. The API, agent tools and UI never open the truth database.

## 4. Shared contracts

Create only if missing. Keep them exactly as written, so any workstream can use them.

**C1. Pack mechanism** (`datagen/scenarios/base.py`, `datagen/cli.py`, `config/scenarios.yaml`)
- `Scenario` gets `pack: ClassVar[str] = "core"`. The five existing classes keep `"core"`.
- `config/scenarios.yaml` gets a top-level `packs:` section (same shape as `scenarios:`). It is never counted in `planted`.
- `cli.generate` runs core scenarios first in today's order, then packs in the fixed order `hard_negatives`, `evasive`, `injection`, `ring`, after all core data has been drawn. Flag: `--packs hard_negatives,evasive,injection,ring` or `all`. Default: none.
- `add_truth` takes optional keyword fields stored on the truth record: `pack`, `difficulty`, `expected_alert` (bool, default true), `acceptable_dispositions` (default the primary), `ring_id`, `ring_role`, `injection_vector`.
- `dataset_meta` stores `seed`, `mode`, `packs` and `split`.

**C2. Eval protocol** (`config/eval_protocol.yaml`, `evals/protocol.py`)
- Contents: seeds (core, dev, test range, demo), `sealed_splits: [test]`, the cost matrix, Wilson interval level. Loaded into a Pydantic model with `extra="forbid"`.
- Cost matrix (expected, predicted): close/escalate 1, close/str_draft 4, escalate/close 3, escalate/str_draft 2, str_draft/close 10, str_draft/escalate 3, all matches 0. A prediction inside `acceptable_dispositions` costs 0.

**C3. Identity** (`backend/app/core/identity.py`, `Role` in `domain/enums.py`)
- `Role` is a `StrEnum`: `analyst`, `senior_reviewer`, `auditor`. `Identity` is a frozen dataclass: `user_id`, `role`, `is_service`.
- Until WS-F lands, code that needs an identity uses a default `Identity("analyst-1", Role.ANALYST, False)`.

**C4. Fake LLM provider** (`backend/app/llm/fake_provider.py`)
- Test-only, never selectable through `LLM_MODE`. Scripted behaviours: ok, HTTP 429 with `Retry-After`, timeout, invalid JSON then valid, always invalid, HTTP 500. Records every request, so tests can inspect prompts.

**C5. In-memory ports** (`backend/app/repositories/memory/`)
- In-memory implementations of `LedgerPort`, `GetPort`, `ComplaintPort` and `TransactionScanPort`, built from a `FinalLedger` and a `GenContext`. The same contract tests run against the Mongo and memory versions.

## 5. Code style and file tree

### Style rules (all new and changed code)

**Python**
- `from __future__ import annotations`, full type hints, Google-style docstrings (purpose, args, returns, raises) on every public function and class. A module docstring on every file saying its role and who calls it.
- Small functions (about 40 lines or fewer), early returns, nesting depth of 3 or less. Files about 250 lines or fewer, one class per file for classes. Split before a file grows.
- Names describe behaviour (`fifo_exit_minutes.py`, not `utils.py`). No `utils.py` or `helpers.py`.
- Closed sets are `StrEnum`. No magic numbers or strings: thresholds, limits, model names and timeouts come from `config/*.yaml` or settings. Config models use `extra="forbid"`.
- `domain/` stays pure: no I/O, no FastAPI, PyMongo or LangGraph. Services receive dependencies through constructors. No globals, no `import db` in a node.
- Errors come from the `DomainError` hierarchy and are mapped in one place (`api/error_handlers.py`).
- Logging through the logger factory with `case_id` and `run_id`. No `print`, except in CLI entry points.
- Async for all I/O. No blocking calls on the event loop.
- Comments say why, never what.

**Tests**
- `tests/unit/<area>/test_<behaviour>.py`, markers `unit` and `integration`. Pure functions are table-driven. No sleeps (use the `Clock` abstraction). Integration tests only use scratch databases.

**Frontend**
- Feature folders, one data hook per resource, no fetching inside presentational components. Strict TypeScript, no `any`. Components about 200 lines or fewer. Formatting only in `lib/format.ts`. Colour is never the only signal. Live regions use `aria-live="polite"`.

**Git**
- Short, literal, plain messages (`add fifo exit matching`). Stage specific files. Never `git add .`. Do not push.

### Target tree (new and changed only)

```text
config/
  eval_protocol.yaml            # new: seeds, splits, cost matrix
  scenarios.yaml                # changed: packs section
  scoring.yaml                  # changed: suppression, outflow rename, ring floor
  llm.yaml                      # changed: tokens per minute, tool_loop, ollama
backend/app/
  core/identity.py              # new: Identity (C3)
  domain/
    metrics.py                  # changed: FIFO matching, ring_peer_count
    enums.py                    # changed: Role, new collection and status names
    network.py                  # new: pure ring clustering
    policy/counterfactual.py    # new: pure what-would-change logic
  repositories/
    memory/                     # new: in-memory ports (C5)
    mongo/                      # new: users_repo, sessions_repo, feed_repo, run_events_repo,
                                #      suppressions_repo, rings_repo, network_repo, eval_sweeps_repo
                                # changed: audit_repo, transactions_repo, index_plan, validators
  services/
    auth_service.py             # new
    feed_service.py             # new
    ring_service.py             # new
    policy_simulator.py         # new
    insights_service.py         # new
    report_export.py            # new
    mock_tools.py               # new: mock tool registry (suppress, feedback, linked alerts)
    detection.py  case_runner.py  event_bus.py  action_service.py   # changed
  graph/
    nodes/reviewer.py           # new: reviewer_gate
    builder.py  edges.py  nodes/investigate.py                       # changed
  agents/
    text.py  tools/flow_tools.py                                     # changed
    prompts/*.v2.md                                                  # new
  llm/
    fake_provider.py  ollama_provider.py  rate_limiter.py            # new
    client.py  http_providers.py                                     # changed
  api/
    security.py                 # new: get_current_user, require_role
    routers/auth.py  feed.py  insights.py  policy.py                 # new
    schemas/auth.py  feed.py  insights.py  policy.py  (and models for existing routes)
datagen/
  scenarios/hard_negative.py  evasive.py  injection.py  ring.py      # new
  staged.py                     # new: split ledger into history and incoming
  plant.py                      # new: add one fresh account
  factories/network.py          # new: devices and logins
  cli.py  writers.py  validate.py                                    # changed
evals/
  gate.py  snapshot.py  sweep.py  bench.py  protocol.py              # new
  harness.py  metrics.py  cli.py  check_policy.py                    # changed
tests/
  support/                      # shared fixtures and builders
  unit/{domain,llm,datagen,api,services,evals}/
  integration/
frontend/src/
  features/monitor/  governance/  network/  auth/                    # new
  lib/useFeedStream.ts  auth.ts                                      # new
.github/workflows/ci.yml                                             # new
docs/
  assurance/{BASELINE.md, PREREGISTRATION.md, core_snapshot.json, eval_log.jsonl, results/}
  MODEL_CARD.md  DEPLOY.md  adr/  demo/DEMO_SCRIPT.md
```

## 6. Workstreams

### WS-A: Quality gate and test foundation

**Depends on:** nothing. **Goal:** change anything and know within a minute whether something broke.

1. **Baseline.** Run `uv sync`, `ruff`, `mypy` (strict scope) and the existing pytest files. Write counts and failures to `docs/assurance/BASELINE.md`. Fix blockers by category, one commit per category. Measure Atlas size with `dbstats`. Verify how `ensure_collections` updates validators on an existing collection.
2. **Gate command** `uv run gate` in `evals/gate.py`. Stages in order: `ruff check` and `ruff format --check`, `mypy`, `pytest -m unit`, core snapshot, then frontend `lint`, `build` and `test` (skipped with a notice if the script does not exist yet). `--full` adds `pytest -m integration`, `check-policy` and `smoke` in fallback mode. `--keep-going` runs every stage.
3. **Core snapshot** `evals/snapshot.py`. Generate seed 42 with 300 customers in memory and write `docs/assurance/core_snapshot.json`: a dataset hash over customers, accounts, counterparties and ledger rows excluding transfer ids, plus for each of the 40 planted accounts the metrics, fired signals, mitigators, score and disposition. Use the in-memory ports (C5). `--compare` prints every account that moved. A unit test regenerates it and asserts equality.
4. **In-memory ports** (C5) and the **fake provider** (C4), if missing.
5. **CI and hooks.** `.github/workflows/ci.yml` (Python 3.12 with uv, a `mongo:7` service container, a frontend job running the gate) and `.pre-commit-config.yaml` (ruff, ruff-format, local mypy).
6. **Unit tests**:
   - each signal and mitigator at its boundary values, read from `config/scoring.yaml`;
   - `score()` sum, floor at 0, ceiling at 100;
   - `decide()` table-driven over every band, the caution band, STR conditions and the hard floor;
   - the action planner for each playbook rule;
   - `compute_metrics` with small hand-computed examples (exit time, pass-through, retention, turnover multiple, z-score, structured share);
   - Hypothesis properties: score is within 0 to 100, mitigators never raise a score, result does not depend on signal order;
   - LLM client with the fake provider: 429 then success, timeout moves to the fallback model, invalid then valid JSON, invalid twice gives a template fallback, cache hit;
   - provider contract suite run against the fake provider and against Groq and Gemini using `httpx.MockTransport`.
7. **Integration tests** (scratch databases): audit append, verify and tamper detection; a fallback-mode graph run for one mule and one seller.

**Done when:** `uv run gate --full` is green, the snapshot test passes, `BASELINE.md` is committed, and the fake provider is used by at least five tests.

### WS-B: Metric correctness and policy 1.1.0

**Depends on:** nothing. **Goal:** fix known logic flaws in the metrics as one isolated change.

1. **Capture a baseline first.** Add `--json` to `check-policy` and save the current results to `docs/assurance/results/policy-1.0.0.json` before editing code.
2. **FIFO matching** in `domain/metrics.py` for exit time and pass-through:
   - process credits oldest first, with a list of later debits and their **remaining** amounts;
   - allocate from the earliest unconsumed debit until the matched amount reaches `exit_match_ratio` (exit time) or the 24-hour window ends (pass-through);
   - exit time is the timestamp of the debit that completes the match, and an unmatched credit lasts until `window_end`;
   - a consumed debit is not available to later credits.
   Document the known limit: a sweep that includes pre-window balance is attributed to the oldest credits first. Add tests that fail on the old code (two overlapping credits sharing one debit).
3. **Naming and boundary.** Rename the detector's `pass_through` (a plain `min(out / in, 1)`) to `outflow_ratio` in code and YAML (`min_outflow_ratio`). Keep the metric `pass_through_ratio`. Make the `dormant_or_new` signal use `>=` like the detector.
4. **Effect on results.** Compare against the saved baseline and list every account whose score or disposition moved, with the reason. Retune only if needed, using core and dev seeds (use `uv run sweep` if WS-D exists, otherwise scratch databases). Bump `policy_version` to `policy-1.1.0` and `version` in `scoring.yaml`. Update the README results, and the snapshot in its own commit if WS-A exists.

**Done when:** FIFO tests fail on the old code and pass on the new, core stays 40/40 with 0 mules closed (or the change is reported with reasons), and the baseline and new results files are committed.

### WS-C: Prompt safety and cache stability

**Depends on:** nothing (uses the fake provider, C4). **Goal:** close the injection routes and make re-runs hit the cache.

1. **Generalise untrusted text** in `agents/text.py`: `clean_text` (strip control characters, limit length) and `untrusted(label, values)`. Wrap and clean every free-text field that reaches a prompt: KYC occupation and city, customer and holder names, counterparty names in tool results. Where names are not needed for reasoning, use stable aliases (`Sender 1`) instead.
2. **Detection.** Extend `looks_like_instruction` (more patterns, including transliterated Hindi such as "pichle nirdesh ignore karo"). Replace `flow:remark_injection` with `input:instruction_like_text`, which names the field.
3. **Evidence aliases (D1).** In `LiveNarrativeWriter`, `LiveCritic` and any prompt that lists evidence, render ids as `E1..En` in a stable order. Map aliases back to real ids when parsing, drop unknown aliases, and keep the existing guards.
4. **Prompt files.** New `profiler.v2.md`, `flow_analyst.v2.md`, `narrative.v2.md`, `critic.v2.md`. The version is stamped on runs and cache keys as today.
5. **Tests.**
   - Prompt hygiene: for each free-text field, build the prompt with an injection payload and assert it appears only inside `<untrusted_data>` blocks.
   - Cache stability: run the same case twice with the fake provider and assert the second narrative and critic calls are cache hits.

**Done when:** both tests pass, and a live smoke run (`uv run smoke --mode live`, if a key is available) still passes. If no key is available, state that it was not run.

### WS-D: Data packs and evaluation protocol

**Depends on:** nothing (uses C1, C2, C5). **Goal:** honest numbers from data the policy has not seen.

1. **Pack mechanism (C1)** and the three packs below. Counts and numbers live in `packs:` in YAML. The generator must satisfy `expected_alert`, which the coverage check verifies, so tune parameters until it does.

   | Pack | Variant | Design | `expected_alert` | Expected (acceptable) |
   | --- | --- | --- | --- | --- |
   | hard_negatives (12) | `wedding_collection` x3 | A parent collects wedding gifts: 25 to 40 relatives send 2,000 to 10,000, most paid to caterer and venue within days | true | close |
   | | `tuition_fees` x3 | A tutor: 18 to 30 parents pay fees at month start, rent and a helper paid out | true | close |
   | | `flash_sale_seller` x3 | Online seller: 150+ small orders in 3 days, about 8% refunded, 80% to a supplier after 2 days, 100 days of history | true | close |
   | | `pg_owner` x3 | Paying-guest owner: about 20 tenants pay rent on the same days monthly, loan EMI and maintenance out | true | close (escalate for one arguable variant) |
   | evasive (12) | `slow_drip` x3 | 9 to 12 senders per 14 days over 6 weeks, money out in 3 to 6 hours | **false** | escalate (str_draft) |
   | | `aged_slow_exit` x3 | Account 400 to 900 days old, high declared turnover, exit in 2 to 5 hours, 20 to 35% kept, 18 to 24 senders | true | escalate (str_draft) |
   | | `warm_up_senders` x3 | 20 senders, 12 of whom paid small amounts in the prior 90 days | true | escalate (str_draft) |
   | | `business_cover` x3 | Registered as "trader" with high declared turnover, exits in under an hour | true | escalate (str_draft) |
   | injection (8) | one per vector | A classic mule with the payload in: a remark (override), a remark (fake system message), a counterparty name, the KYC occupation, the customer name, a remark with a spoofed `EVD-` id, a remark with tipping-off bait, a transliterated Hindi remark | true | str_draft |

   Rules: no scenario name, flag or hint in any operational field, id or remark (the payload is the only test content and must not say "test" or "planted"). Remarks stay at 140 characters or fewer. Hard negatives need believable backstories, remarks and mitigating history.
2. **Coverage check.** In `validate.check_coverage`, an alert must exist exactly when `expected_alert` is true.
3. **Protocol (C2)** and `evals/protocol.py`.
4. **Sweep** `uv run sweep --seeds 100-199 --packs all [--split dev|test] [--save]`. For each seed: generate in memory, run the real detector rules, `MetricsService` (through the in-memory ports), `score()` and `decide()`. Report per pack and overall: detector recall and precision, accuracy, mules closed, false STR rate, cost-weighted error, a confusion matrix and **Wilson 95% intervals** pooled across seeds. Write `docs/assurance/results/<name>.json`, print a table, append one line to `docs/assurance/eval_log.jsonl` (time, git commit, command, split, seeds, packs, policy version, config hash, summary). `--save` stores the aggregate in `eval_sweeps`. Refuse `--split test` unless `docs/assurance/PREREGISTRATION.md` is committed.
5. **CLI.** `check-policy` and `evals` get `--pack` and `--scope`.
6. **Data contract tests** (`tests/unit/datagen/`):
   - same seed and packs give the same dataset (hash);
   - `check_ledger` passes for seeds 1 to 5 with all packs;
   - the core hash (without transfer ids) is identical with and without packs;
   - each scenario produces the metrics it promises, and for evasive scenarios the signals that should **not** fire do not fire;
   - the detector alerts exactly where `expected_alert` is true.
7. **Pre-registration.** Write `docs/assurance/PREREGISTRATION.md` defining each metric precisely and setting the initial targets below. Targets may be revised only before the first test run, and each revision is logged in the file.

   | Metric | Initial target |
   | --- | --- |
   | Mules closed (core mules and injection pack) | 0 |
   | Core pack disposition accuracy | at least 0.95 |
   | Detector recall on non-evasive planted mules | at least 0.99 |
   | Hard negatives closed | at least 0.70 |
   | Hard negatives sent to STR draft | at most 0.05 |
   | Evasive pack | no target, reported as limitations |
   | Injection obeyed and unwrapped payload leaks | 0 |
   | Citation validity and tipping-off violations | 1.0 and 0 |
   | Ring recovery (WS-I) | precision at least 0.90, recall at least 0.80, false links on family negatives 0 |
8. **Evals page.** Group results by pack with a filter, show detector recall and precision as separate tiles, a known-failures table linking to cases, and a seed-sweep chart with intervals.
9. **Use the findings.** Run the dev split and report where hard negatives and evasive mules fail. Fix a gap only with one registered signal or mitigator plus a YAML entry (weights still sum to 100), retune on dev seeds only, re-check core and dev, and bump the policy version.

**Done when:** packs seed cleanly, the coverage check passes, contract tests pass, the core hash is unchanged, and a dev sweep of 5 seeds runs in under a minute. **Then stop** and report the dev results. Do not run the test split until the user confirms the pre-registration.

### WS-E: Live monitoring (staged mode)

**Depends on:** nothing. **Goal:** the demo starts with data and no alerts, and the audience watches the detector work.

1. **Detector** (`services/detection.py`):
   - move the per-account aggregation into a MongoDB aggregation (`$match` on `ts`, `$group` by account, distinct senders with `$addToSet` and `$size`). Rule evaluation stays pure. A test must show identical results to the old Python version on the core data;
   - alert and case ids come from `counters.next_ids`, and a scan is single-flight (an `asyncio.Lock`);
   - dedupe per D2: no alert if the account has an open case or a case closed within `suppression_days`, unless inflow is at least `reopen_if_inflow_multiple` times the old trigger inflow;
   - alerts store `detected_at_sim` in staged mode.
2. **Mock tools** (`services/mock_tools.py`): a registry from `mock_tool` name to a side effect. `suppress_similar_alerts` writes `suppressions`, `store_feedback` writes `detector_feedback`. `execute_actions` calls the registry. All other actions keep today's mock result.
3. **Staged seed** (`datagen/staged.py`): `uv run seed --mode staged`. Split the finalised ledger at `window_start_ts`: earlier rows go to `transactions`, the rest to `transactions_incoming` (same shape and `_id`). Complaints split by `reported_at` into `complaints` and `complaints_incoming`. Set `accounts.balance` to the end-of-history balance. Do not run the detector. Create `sim_state` (`status: idle`, `sim_now = window_start`). Fail with a clear message if any account opens inside the window. `dataset_meta.mode` is `instant` or `staged`.
4. **Feed service** (`services/feed_service.py`, single-flight):
   - `advance()` copies the next step (`feed.step_hours`, default 24) from incoming into `transactions` (idempotent on duplicate key), updates the touched account balances in one bulk write, runs the detector with `window_end = new sim_now`, updates `sim_state`, and publishes `feed_tick`, `alert_created` and `feed_done` on the existing event bus under run id `feed`;
   - `start` runs `advance()` every `feed.tick_seconds` (default 3) in a background task. `pause`, `step` and `scan` (detect now, no release) are supported;
   - `reset` removes released data (`ts >= window_start`) and the alerts, cases, runs, node executions, evidence, reports, actions, decisions and audit records of this dataset, and rewinds the clock. It is refused while a run is active.
5. **Investigation window (D14).** A `SimTimePort` gives `load_case` the simulated now (`None` in instant mode). `load_case` sets the window to the window length ending at that time, falls back to `alert.window` otherwise, and stores `window` and `evidence_as_of` on the run. A completed run is never reused for a different `evidence_as_of`. "Re-run investigation" is the explicit refresh.
6. **API** (`api/routers/feed.py`, `api/schemas/feed.py`, thin controllers):

   | Route | Purpose | Access |
   | --- | --- | --- |
   | `GET /feed` | state, counts, sim_now, day n of 14 | any |
   | `POST /feed/start`, `/pause`, `/step`, `/scan`, `/reset` | controls | requires `DEMO_MODE=true` (and `senior_reviewer` once WS-F exists) |
   | `GET /feed/transactions?limit=50` | latest released transactions, masked | any |
   | `GET /feed/stream` | SSE | any |

   `GET /config/public` adds `mode`, `demo_mode`, `policy_bands` and `window_days`.
7. **UI** (`features/monitor/`): a Monitor page with data status, controls (Reset asks for confirmation), a virtualised ticker of the latest 50 transactions with filters, a day counter and an alerts counter linking to the queue. `aria-live="polite"`, a pause control and `prefers-reduced-motion` support. Monitor is the landing page in staged mode, the queue in instant mode. The queue shows "no scan yet" when empty, highlights new rows and hides SLA tiles in staged mode. The case header shows "evidence as of". Add `lib/useFeedStream.ts`.
8. **Evals reveal.** `uv run evals --scope staged --at alert|latest` runs and scores the staged cases and adds time-to-detect (days from the first planted credit in the window to `detected_at_sim`).
9. **(optional) Benchmark** `uv run bench`: in memory, generate a large dataset (default 5,000 customers) and time `compute_metrics` and the detector aggregation. On Atlas, report `explain()` for the main queries (stage, documents examined, time) to `docs/assurance/results/bench.md`. State that database-level scale needs a local or CI Mongo.

**Done when:** instant mode and the core snapshot are unchanged; a staged seed leaves zero alerts; stepping through the 14 days raises alerts for planted mules; a closed case does not re-alert the next day; two concurrent scans do not collide; staged seed 42 investigated `--at latest` after the last day matches the instant-mode dispositions for the core 40 (any difference reported and explained).

### WS-F: Access control (auth, roles, maker-checker)

**Depends on:** nothing (creates C3 if missing). **Goal:** make identity and approval real.

1. **Auth** (`services/auth_service.py`, `repositories/mongo/users_repo.py` and `sessions_repo.py`, `api/security.py`, `api/routers/auth.py`):
   - users: `email`, `name`, `role`, `password_hash` (argon2id via `argon2-cffi`), `active`. Sessions in `sessions` with an 8-hour TTL;
   - cookie: random session id, `HttpOnly`, `SameSite=Lax`, `Secure` outside localhost;
   - `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`. CORS allows credentials for the listed origins only, and unsafe methods require an allowed `Origin`;
   - `get_current_user` and `require_role(...)`. Remove `user_id` and `role` from `DecisionRequest` and `ActionPatch`; identity comes from the session. `SESSION_SECRET` is required outside demo and test, otherwise the API refuses to start;
   - `uv run seed --demo-users` creates one user per role with **random passwords printed once**. Nothing is stored in the repo.
   - `evals` and `smoke` run in-process with service identities (`eval-maker`, `eval-checker`). They are never reachable over HTTP.

   | Role | Allowed |
   | --- | --- |
   | `analyst` | view everything, start runs, approve, edit, reject, request more, dismiss noise, patch their own actions |
   | `senior_reviewer` | analyst rights, the reviewer gate, high-risk actions (hold, STR draft), feed controls |
   | `auditor` | read-only on cases, audit, evals and governance pages, audit export |
2. **Maker-checker.** After `apply_decision`, when the final disposition is `str_draft`, a new `reviewer_gate` node (`graph/nodes/reviewer.py`) interrupts. The checker must be a `senior_reviewer` and not the maker, enforced on the server. Approve goes to `execute_actions`. Reject goes to `finalize` with status `returned` and a mandatory reason. Add case status `pending_review`, `POST /cases/{id}/review`, and audit events `review.approved` and `review.rejected` with both ids. Bump `GRAPH_VERSION` to `0.2.0`. The eval harness approves twice with distinct identities.
3. **UI** (`features/auth/`): login page, user chip with role, logout, a Review button and a "waiting for second approval" banner. Hide controls the role cannot use, and also enforce on the server. The SSE hook sets `withCredentials`.
4. **Tests:** 401 without a session, 403 for the wrong role, a body-supplied role is ignored, a maker cannot check their own STR.

**Done when:** all four tests pass, the eval harness still completes 40 cases in fallback mode, and `.env.example` lists `SESSION_SECRET`.

### WS-G: Reliability (audit, events, startup, actions)

**Depends on:** nothing. **Goal:** remove the known weak points around the audit log and runs.

1. **Audit chain** (`repositories/mongo/audit_repo.py`): add `chain_id` (case id or `_global`) and `seq`, with a unique index on `(chain_id, seq)`. `append` reads the last seq, inserts `seq + 1` and retries on a duplicate key error (up to 5 times). The per-process lock stays as an optimisation. Add an `hmac` field, `HMAC-SHA256(AUDIT_HMAC_KEY, hash)`. `verify_chain` checks hashes, sequence continuity and the HMAC, and reports `hmac_unverifiable` when no key is set instead of failing. `GET /cases/{id}/audit/head` returns a signed head (`case_id`, `seq`, `hash`, `hmac`) the auditor can store outside the database.
2. **Event stream:** persist every bus event to `run_events` (TTL 7 days) with a per-run monotonic id. The SSE endpoint writes `id:`, sends a `: ping` comment every 15 seconds and replays only events after `Last-Event-ID`. Simplify `useRunStream`: keep the persisted-state refetch as a safety net, and stop clearing events on reconnect.
3. **Startup sweep (D15):** mark every run with status `running` that this process is not driving as `failed` (`api_restart`), publish `run_failed` and write an audit event. Leave `awaiting_decision` and `pending_review` runs alone.
4. **Action fixes:** the idempotency lookup considers only actions in `proposed`, `approved` or `executed`, so cancelled, rejected and reversed actions do not block a new proposal. Store `evidence_refs: [{id, statement}]` on each action at proposal time, and use it in the UI chip before showing "from an earlier run".
5. **Tests:** tamper with a record, delete one, insert one, swap two, and run two concurrent appends. Each must be detected or serialised. Restart simulation: a `running` run becomes `failed`. Replay with `Last-Event-ID` returns only later events.

**Done when:** the tests pass and the UI audit badge still shows the chain valid after a normal run.

### WS-H: Explainability and governance

**Depends on:** nothing. **Goal:** explain every decision and let a model owner see the effect of policy changes.

1. **Counterfactuals** (`domain/policy/counterfactual.py`, pure): from the stored metrics, hits and policy, compute for each fired signal the score and disposition if it had not fired, for each mitigator the effect of removing it, and for each unfired signal how far its metric is from the threshold. Return the three smallest changes that flip the disposition, with plain text ("if turnover were under 10 times declared, the score would be 60 and the result Escalate"). `GET /cases/{id}/counterfactuals`. UI panel "What would change this?" in `features/case-workspace/`. If only evidence is stored, rebuild `FlowMetrics` from the metric evidence of the latest run. A property test checks consistency with `decide()`.
2. **Sandbox** (`services/policy_simulator.py`, `api/routers/policy.py`):
   - `POST /policy/simulate`: overrides validated by `ScoringConfig` (extra fields forbidden, weights sum to 100). Recompute metrics for the existing cases with bounded concurrency, apply the overrides in memory, and return before and after scores and dispositions and the movers. Nothing is saved;
   - if an eval run exists, join its `eval_results` labels to also show mules closed and accuracy. Otherwise show movement only;
   - `POST /policy/sensitivity`: a grid of `close_below` and `str_at` returning disposition counts (and mules closed when labels exist).
3. **Dashboards** (`services/insights_service.py`, `api/routers/insights.py`): `GET /insights/feedback` returns override and reject rate by signal, analyst agreement rate, closed-after-policy-close rate, and text-only threshold suggestions that are never applied automatically (it reads `detector_feedback` when present, otherwise `decisions`). `GET /insights/operations` returns cases by status, average handling time (run start to decision), tokens per case, fallback rate over time, cache hit rate, and p50 and p95 node latency.
4. **UI** (`features/governance/`): a Governance navigation group with Sandbox (sliders, before and after table, a chart, "Export YAML"), Feedback and Operations. Every chart has a table alternative.

**Done when:** counterfactual and `decide()` agree in tests, the simulator leaves the database unchanged (asserted in a test), and the dashboards render from seeded decisions.

### WS-I: Ring detection and linked cases

**Depends on:** nothing (uses C1). **Goal:** show network thinking without disturbing the single-account policy.

1. **Data** (`datagen/factories/network.py`, `datagen/scenarios/ring.py`): `devices` and `login_events` (sparse: a few events at onboarding and in the 30 days before the window start, never inside the window). Ring pack: one ring of 6 mule accounts for different customers, opened within 3 days of each other 110 to 150 days before the window, 9 to 13 senders each (individually weak), sharing 2 devices and one IP, paying the same one or two beneficiaries. Plus a negative group of 3 family accounts sharing a household device and IP with ordinary activity, different from the ring in surname pattern, opening dates and behaviour. Truth fields `ring_id` and `ring_role`.
2. **Analysis** (`domain/network.py`, pure): edges from shared device, shared IP, shared beneficiary (a counterparty receiving from two or more accounts in the window) and internal transfers. Components by union-find. A cluster is a ring only with at least two edge types or behavioural support from alerted members, so a family sharing a device is not one. Edge weights and thresholds come from config.
3. **Service** (`services/ring_service.py`, `repositories/mongo/rings_repo.py`, `network_repo.py`): store clusters in `rings`, set `ring_id` and `ring_size` on member cases, and raise the priority of member cases (config). Add a fifth read-only Flow Analyst tool, `get_shared_infrastructure`, returning counts and masked ids only. Add `network:*` evidence facts and a typology `coordinated_mule_ring`.
4. **Policy 1.2.0:** `FlowMetrics.ring_peer_count`, and a hard floor in `disposition.hard_floor_ring_peers`: a case with at least that many ring peers is never Close (minimum Escalate). Ring membership adds no points. Re-check core and dev, and bump `policy_version`. The existing `flag_linked_accounts` action gets a mock tool in `mock_tools.py` that raises low-priority alerts (`PT-LINKED-01`) on linked accounts that did not alert.
5. **UI** (`features/network/`): a Ring badge in the queue, a Network tab in the case workspace (React Flow: accounts, devices and IPs masked, beneficiaries, colour by edge type, cluster outline), and a Rings list under Governance.
6. **Evals:** ring recovery precision and recall against `ring_id`, and false links on the family negatives, per sweep.

**Done when:** the core snapshot is unchanged with the ring pack off, a seeded ring is recovered within the pre-registered thresholds on dev seeds, the family negative is not linked, and no ring analysis changes a score.

### WS-J: LLM layer upgrades

**Depends on:** nothing (uses C4 for tests). **Goal:** fewer failures on the free tier, and a more honest agent.

1. **Schema-enforced output.** Check the current Groq documentation for `response_format` with `json_schema` for the models in `llm.yaml`. Use it when supported, and keep JSON mode with the repair loop as the fallback.
2. **Token-bucket limiter** (`llm/rate_limiter.py`): per provider and model, an estimated rolling tokens-per-minute budget (`llm.yaml`, using the `Clock` abstraction). When the budget is exhausted, wait up to the node budget, then fall back to the template. Unit-test with a fake clock.
3. **Tracing guard.** A `TRACING` setting (`off` or `langsmith`, default `off`). At startup, if any `LANGSMITH_*` tracing variable is set while `TRACING` is not `langsmith`, force tracing off for the process and log a warning. When `langsmith` is chosen, log that prompts leave the machine and that only synthetic data is allowed. Do not add Langfuse.
4. **(optional) Tool-choosing Flow Analyst.** `agents.flow_analyst.mode: tool_loop` (default `fixed`). The LLM may request up to `max_tool_calls` calls among the four read-only tools as JSON `{tool, args}` or `{final}`. Arguments are validated by Pydantic, results are wrapped as untrusted, the loop stays inside the node budget, and every call is recorded in `node_executions.tool_calls`. Facts are still produced by code from tool outputs. Any error falls back to `fixed`. Compare both modes on a small live subset (tokens, latency, citation validity, evidence kinds covered).
5. **(optional) `OllamaProvider`** (`llm/ollama_provider.py`) over `httpx` for a free local model, with `MockTransport` contract tests. Mark live use unverified unless Ollama is installed.

**Done when:** limiter and tracing guard have tests, JSON-schema output is used or the reason it is not is recorded in `PROGRESS.md`, and the fallback path is unchanged.

### WS-K: Typed API and frontend quality

**Depends on:** nothing. It touches many files, so run it when no other workstream is in flight. **Goal:** remove hand-copied types and bring the frontend to the stated standards.

1. **Response models** in `api/schemas/` for every route, with `response_model=` on each. SSE event payloads get models too and appear in the OpenAPI schema. `uv run openapi` writes the schema, `npm run gen:api` runs `openapi-typescript` into `src/types/api.generated.ts`. Migrate router by router, re-export from `api.ts` where types match, and delete the hand-written file when empty. CI fails when the generated file is out of date.
2. **Lint and format.** ESLint (typescript-eslint, react-hooks, `no-explicit-any`) and Prettier, with `lint` and `format` scripts. Split components over about 200 lines. Replace `scoreColor` thresholds and `WINDOW_DAYS` with values from `/config/public`.
3. **Tests.** Vitest and Testing Library for `format.ts`, `aggregate.ts`, the stream hooks and the chip components. (optional) One Playwright smoke test (log in, open a case, run it in fallback mode, decide) using the installed Edge (`channel: "msedge"`, no browser download).

**Done when:** `npm run lint`, `npm run build` and `npm run test` pass, no `any` remains, no route lacks a response model, and the generated types compile with the UI.

### WS-L: Demo and documentation

**Depends on:** nothing. Use whatever flags and features exist when you start. If one is missing, leave it out of the demo profile and say so in `PROGRESS.md`.

1. **Demo profile.** `uv run seed --profile demo --reset` means seed 900 with `--mode staged`, all packs, and demo users when they exist. It writes `docs/demo/DEMO_SCRIPT.md` with the case ids per story and talking points. Reading truth stays inside the CLI.
2. **`uv run plant <scenario>`** (`datagen/plant.py`): add one fresh account of a registered scenario to the current dataset, with a fresh id allocator that checks for collisions in the database, and an incremental insert of customers, accounts, counterparties, transactions, complaints and truth. In instant mode it inserts directly and runs the detector, so the case appears within the queue's 15-second refresh. In staged mode it is allowed only before the feed starts (its activity goes to `transactions_incoming`) and refused while the feed runs.
3. **STR export** (`services/report_export.py`): `GET /cases/{id}/report/export?format=pdf|json|md`. PDF with `reportlab` (pure Python). JSON follows a documented illustrative schema built from `str_required_sections`. Every export carries "DEMO DRAFT. Not a regulatory filing." The STR due date is read from `playbook.yaml` and keeps its TODO verify note. Exports are watermarked as draft until checker approval, if WS-F exists.
4. **Model card** `docs/MODEL_CARD.md`: intended use and out-of-scope, data and its synthetic limits, the circularity caveat (generator and policy share an author, so anchor scenarios to published red-flag sources and cite them), metrics from `eval_log.jsonl` with intervals, known failure modes, human oversight, change control and policy version history, security notes.
5. **ADRs** in `docs/adr/`, one short file each for D1 to D16.
6. **README.** Modes (instant and staged), packs, evaluation protocol and splits, security model and roles, the demo walkthrough, known limits (circularity, schema reset policy, free-tier limits, unverified Gemini and Ollama, untested deployment), and a demo GIF placeholder with capture instructions. Update the results table from `eval_log.jsonl`, with pre-registered targets met or missed, misses first.
7. **Deployment files.** Dockerfiles for the API and frontend, a `docker-compose.yml` for the whole stack, and `docs/DEPLOY.md` for a hosted read-only demo (Atlas M0, a free host, `LLM_MODE=fallback`, instant mode, pre-seeded). Docker is not available on the dev machine, so add a CI job that builds the images, and state plainly that deployment was not tested.
8. **Demo walkthrough** (about 8 minutes, in `DEMO_SCRIPT.md`): Monitor and Start feed; alerts appear; a classic mule through agents, report, approval and audit chain; a hard negative that Closes with mitigator bars; an evasive mule in the caution band and one the system misses, shown honestly; an injection case whose remark is shown as untrusted while the report does not follow it; a ring in the Network tab; the Evals page by pack and the seed sweep; `uv run plant` adding a fresh case live. Default to `LLM_MODE=fallback`, with one live run rehearsed beforehand.

**Done when:** a clean clone can follow the README to a working demo, the docs listed above are committed, and anything unverified is labelled as such.

## 7. What not to do

- Do not change the core seed-42 dataset, its truth labels or its ids (other than the documented transfer id renumbering).
- Do not open the truth database from the API, agent tools or the UI path.
- Do not tune or adjust anything after looking at the test split. Do not run it before the user confirms the pre-registration.
- Do not weaken a test, widen a label set or loosen a threshold to make a result pass. Report the failure.
- Do not add an auth bypass, a default admin password or credentials in the repo.
- Do not enable tracing, or send prompts anywhere new, by default.
- Do not run `uv run seed --reset` on the main databases without asking.
- Do not invent regulatory facts.
- Do not remove existing features, screens or commands. Extend them.
- Do not commit `.env`, keys or generated credentials.

## 8. Reporting

At the end of each workstream, add a short entry to `PROGRESS.md` and tell the user: what changed, the check output, any deviation from this document and why, what could not be verified (for example Docker, Ollama, Gemini, hosted deployment), and the numbers that moved. Keep it plain and literal. When all chosen workstreams are done, summarise results against the pre-registered targets, with the misses first.

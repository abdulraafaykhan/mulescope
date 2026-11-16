# PROGRESS

Checklist of build phases. If context is lost, continue from the first unchecked item.
Source of truth for stack, data model, graph, scoring and UI: `docs/BUILD_PROMPT.md`.
Process, testing and scope follow the latest user instructions (no specs, no test suites,
smoke commands only, commit after each phase). This run stopped after phase 3 as asked.

## Phases

- [x] Phase 0: finish M0 (container, API layer, main.py, entry points). Smoke: `/health` ok.
- [x] Phase 1: synthetic data and detector. Smoke: all 40 planted accounts alerted, 0 organic, seed ~55-70 s on Atlas.
- [x] Phase 2: domain logic. Smoke: `uv run check-policy` 40/40 (100%), 0 mules closed.
- [x] Phase 3: API and graph in fallback mode. Smoke: `uv run smoke` mule -> STR draft, seller -> Close, ~3 s per run, audit chains valid; resume after API restart verified.
- [ ] Phase 4: live LLM agents (Groq/Gemini provider, cache, limiter, prompts, structured output). Keys in `.env` are empty, so fallback stays on.
- [ ] Phase 5: analyst UI (React + Vite + TS, queue, case workspace, flow graph, agents stepper over SSE, actions, audit, diagnostics).
- [ ] Phase 6: `uv run evals --mode fallback|live`, Evals page, README.

## State of the build

Backend (`mulescope/backend/app`):
- `core/`: settings (API has no truth URI), container (async client + sync checkpointer client), wiring, logging, errors, config loaders.
- `domain/`: enums, `metrics.py` (all section 8.1 metrics), `signals/` (registry + 9 risk signals + 4 mitigators), `policy/` (config models, detector rules, scoring, disposition, typology, action planner).
- `repositories/mongo/`: bootstrap (validators + indexes), one class per collection, audit hash chain with `verify_chain`.
- `services/`: detection (PassThroughDetector), metrics, case_runner (background graph runs, interrupt/resume), case_query (UI read models), action_service, event_bus (SSE).
- `agents/`: template Profiler, Flow Analyst (4 read-only tools), Narrative Writer, Critic (code checks); text helpers incl. `<untrusted_data>` and injection detection.
- `graph/`: state, deps, instrument decorator (node_executions + audit + stream events), nodes, edges with loop caps, builder (MongoDBSaver).
- `api/routers/`: `/health`; `/api/v1` config, alerts (list, get, detect), cases (list, detail, runs, decision, evidence, report, actions, flow, timeline, transactions, audit verify), accounts (get, summary), actions (patch), audit, runs (SSE stream, diagnostics), evals (read; POST points to the CLI).

Data (`mulescope/datagen`): personas engine (NumPy vectorised), counterparty pools, 5 scenario classes / 16 variants / 40 planted accounts, ledger builder (double entry, running balances, time-ordered transfer ids), writers, validation, `--preview`.

Scripts: `uv run seed`, `uv run dev`, `uv run check-policy`, `uv run smoke`, `uv run evals` (stub).

## Decisions

- MongoDB is Atlas from the workspace `.env` (read-only). No local Docker on this machine.
- Settings read both `mulescope/.env` and the workspace `.env`; empty `*_API_KEY=` counts as unset.
- `/health` at the root path; all other routes under `/api/v1`.
- Checkpointer: `MongoDBSaver(ttl=7 days)` on a dedicated sync client built off the event loop. Resume after restart works, so MemorySaver was not needed.
- Planted alerts: five parametrised classes (mule 10, seller 10, group 8, dormant 6, ambiguous 6); the injected-remark mule is a mule variant.
- Persona templates live in `datagen/factories/personas.py` as data; scenario parameters in `config/scenarios.yaml`.
- Account and customer ids are random 6-digit (`ACC-123456`) so id order carries no hint of planted accounts; transfer ids are assigned in time order.
- Mules sweep the whole balance (not just new money) leaving a few hundred rupees.
- Detector: three rules (fan-in pass-through, high-value pass-through, dormant reactivation) on the 14-day window ending at `as_of`. Alerts/cases use the wall clock for `created_at` and SLA so the queue is current.
- `median_exit_minutes` = minutes until cumulative outflow after a credit reaches 90% of it (simpler and more robust than strict FIFO).
- Policy tuning (iteration 2 of 3): `low_retention` threshold 0.05 -> 0.2, classic mules declare a low turnover. Caution band: 35-39 -> Escalate; 65-69 with STR conditions -> STR draft. Victim-linked 1-2 senders = 6 points, 3+ = 15.
- Critic word lists, STR section headings and required evidence kinds live in `config/playbook.yaml`.
- Evals and smoke run from the CLI only, because the API process never opens the truth database.
- Faker 40.54.0 and NumPy 2.5.5 added (both in the section 2 stack, pinned).

## Known gaps

- Phases 4-6 not built: no live LLM agents, no UI, no eval harness or README update.
- Separate reviewer gate (maker-checker for STR) skipped; one analyst gate only.
- Most API responses are plain dicts, not dedicated response models.
- SSE has no heartbeat; event history is in memory (a reconnect after an API restart only sees new events).
- Detector scans only the window ending at `as_of`, not a stepped rolling window. Organic alerts are 0, so detector precision on background noise is not really exercised.
- Existing pytest files from the earlier spec run are kept but were not run or updated in this phase; some will now be stale.
- mypy strict, ruff, CI and pre-commit were not run in this phase (by instruction).
- Audit chain lock is per process; two API processes could fork a case chain.
- Customer-facing tipping-off check is keyword based.
- About 590 counterparties instead of the target of 600.

## Commands (PowerShell, from `mulescope/`)

```powershell
uv sync
uv run seed --seed 42 --customers 300 --reset   # generate + load + detect (~1 min on Atlas)
uv run seed --preview ACC-123456                 # one account's 14-day story
uv run check-policy                              # expected vs predicted for the 40 planted alerts
uv run smoke                                     # mule + seller through the graph, auto-approve
uv run dev                                       # API on http://127.0.0.1:8000 (/health, /docs)
```

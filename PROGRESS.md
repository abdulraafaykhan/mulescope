# PROGRESS

Checklist of build phases. If context is lost, continue from the first unchecked item.
Source of truth for stack, data model, graph, scoring and UI: `docs/BUILD_PROMPT.md`.
Process, testing and scope follow the latest user instructions (no specs, no test suites,
smoke commands only, commit after each phase). Phases were built in the order 5, 6, 4 as asked.

## Phases

- [x] Phase 0: finish M0 (container, API layer, main.py, entry points). Smoke: `/health` ok.
- [x] Phase 1: synthetic data and detector. Smoke: all 40 planted accounts alerted, 0 organic, seed ~55-70 s on Atlas.
- [x] Phase 2: domain logic. Smoke: `uv run check-policy` 40/40 (100%), 0 mules closed.
- [x] Phase 3: API and graph in fallback mode. Smoke: `uv run smoke` mule -> STR draft, seller -> Close, ~3 s per run, audit chains valid; resume after API restart verified.
- [x] Phase 4: live LLM agents (Groq/Gemini providers, `llm_cache`, semaphore of 2, retry with backoff, schema repair, versioned prompts, per-node template fallback, critic code + LLM checks). Smoke: an offline check with a fake provider passed (429 retry, cache hit, invalid output -> template fallback, narrative guards, critic). `uv run smoke --mode live` was not run: no `.env` / Mongo and no Groq or Gemini key in this clone, so fallback stays on.
- [x] Phase 5: analyst UI (React + Vite + TS, queue, case workspace, flow graph, agents stepper over SSE, actions, audit, diagnostics). Smoke: `npm run build` passes (tsc clean). Not yet clicked through against a live API: this clone has no `.env`, so the API cannot reach Mongo (see Known gaps).
- [x] Phase 6: `uv run evals --mode fallback|live` (harness, resumable with `--resume`), Evals page, README. Smoke: CLI imports and `--help` parse. Not yet run end to end, because there is no `.env` / Mongo in this clone. First command once the `.env` is back: `uv run evals --mode fallback`.

## State of the build

Backend (`backend/app`):
- `core/`: settings (API has no truth URI), container (async client + sync checkpointer client), wiring, logging, errors, config loaders.
- `domain/`: enums, `metrics.py` (all section 8.1 metrics), `signals/` (registry + 9 risk signals + 4 mitigators), `policy/` (config models, detector rules, scoring, disposition, typology, action planner).
- `repositories/mongo/`: bootstrap (validators + indexes), one class per collection, audit hash chain with `verify_chain`.
- `services/`: detection (PassThroughDetector), metrics, case_runner (background graph runs, interrupt/resume), case_query (UI read models), action_service, event_bus (SSE).
- `agents/`: template Profiler, Flow Analyst (4 read-only tools), Narrative Writer, Critic (code checks); text helpers incl. `<untrusted_data>` and injection detection.
- `graph/`: state, deps, instrument decorator (node_executions + audit + stream events), nodes, edges with loop caps, builder (MongoDBSaver).
- `api/routers/`: `/health`; `/api/v1` config, alerts (list, get, detect), cases (list, detail, runs, decision, evidence, report, actions, flow, timeline, transactions, audit verify), accounts (get, summary), actions (patch), audit, runs (SSE stream, diagnostics), evals (read; POST points to the CLI).

Data (`datagen`): personas engine (NumPy vectorised), counterparty pools, 5 scenario classes / 16 variants / 40 planted accounts, ledger builder (double entry, running balances, time-ordered transfer ids), writers, validation, `--preview`.

Scripts: `uv run seed`, `uv run dev`, `uv run check-policy`, `uv run smoke`, `uv run evals` (stub).

Frontend (`frontend`, React 19 + Vite 8 + TS 7 + Tailwind 4):
- `src/types/api.ts`: every API type in one hand-written file, mirroring `services/case_query.py`, the Mongo repositories and the graph node documents.
- `src/lib/`: fetch client with the error envelope, one TanStack Query hook per resource, `useRunStream` (SSE with reconnect + refetch), formatters (INR Indian grouping, IST, masking), colour/status metadata.
- `src/features/`: queue, case-workspace (header + decisions, entity strip, score breakdown, evidence, timeline, transactions, report), flow-graph (React Flow + dagre account cards), agents (live stepper), actions, audit (audit log + diagnostics drawer), account drawer, evals.
- Start: `cd frontend; npm install; npm run dev` and open http://localhost:5173 (API must be on http://127.0.0.1:8000 via `uv run dev`). Override the API URL with `VITE_API_URL` in `frontend/.env.local`.

## Decisions

- MongoDB is Atlas from the single root `.env` (read-only). No local Docker on this machine.
- Repo layout flattened: everything that lived in `mulescope/` (backend, frontend, config, datagen, evals, tests, pyproject.toml, uv.lock, docker-compose.yml, .env.example) now sits at the repo root, moved with `git mv`. One `.gitignore`, one `README.md`, one `.env`. Old `.kiro/specs/m0-scaffold` text still says `mulescope/`; it is history and was left alone. `docs/BUILD_PROMPT.md` (the original spec) also keeps its original tree.
- At flatten time the Atlas cluster in the root `.env` held no MuleScope data: `mulescope` had only empty `checkpoints` / `checkpoint_writes`, and `mulescope_truth` was empty. So `uv run check-policy` and `uv run smoke` ran cleanly but had nothing to evaluate. Seeding was not run (by instruction). `frontend/package.json` had lost its devDependencies in the phase 5 commit; they are restored with the same pinned versions.
- Settings read one `.env` in the repo root (the former `mulescope/` subfolder was flattened away); empty `*_API_KEY=` counts as unset.
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
- UI: API types are hand-written in `src/types/api.ts` (by instruction) rather than generated with openapi-typescript, because most routes return plain dicts with no response model.
- UI: shadcn/ui primitives are hand-written in `components/ui/` in the same Tailwind style (no shadcn CLI, no Radix). Fonts self-hosted with `@fontsource-variable` (Inter, JetBrains Mono). `lucide-react` added for icons; `@tanstack/react-virtual` for the transactions table; `react-router` for routes. All pinned exactly.
- UI SSE: the stream has no heartbeat and its history lives in API memory. `useRunStream` reconnects with backoff (1 s to 10 s), clears live events on each connect (the server replays history), and refetches the case and node_executions on every drop. The Agents stepper layers live events over persisted node_executions, and case/diagnostics poll every 3 s while a run is `running`, so a silent drop or API restart cannot leave it stale.
- UI score breakdown is built from the `signal` evidence items (fired signals and mitigators with points); there is no separate breakdown endpoint.
- UI decisions: Approve and Request more post directly; Edit, Override and Reject open a dialog (override and reject require a reason, matching the API rules).
- Evals: `evals/harness.py` starts a run per planted case, auto-approves, and saves each result as soon as it is known (`_id = eval_run:case`). `--resume` (latest unfinished run of the mode) or `--resume EVAL-0003` skips cases already evaluated without error. A run stays `running` until all 40 are in without error. A case run left `running` by a dead process is marked failed and restarted.
- Evals metrics: predicted is the case's policy disposition after the run. Citation validity is cited ids that exist in the run's evidence divided by all cited ids. Claim coverage uses the critic's claim-line rule. Fallback rate counts LLM-agent nodes that used the template. Latency is harness wall time per case, including the auto-approve resume.
- `eval_results` store the scenario name, label and expected disposition so the Evals page can show per-scenario pass/fail. They are written only by the CLI, and no agent tool reads that collection. This deviates from "no answers inside" for eval results; the truth database stays the only source of labels.
- README states that the weights were tuned on the seed-42 alerts (in-sample), that seed 7 is a synthetic-to-synthetic check, and that three mules scoring 65, 65 and 68 reach STR only through the caution band.
- LLM transport: Groq (OpenAI-compatible chat, `response_format: json_object`) and Gemini (`generateContent`, `responseMimeType: application/json`) over `httpx` (pinned 0.28.1, already in the lock through langchain-core), instead of two vendor SDKs. Structured output = JSON mode + Pydantic validation + one repair retry, not `with_structured_output` (no LangChain chat-model packages in the stack).
- Models (`config/llm.yaml`, TODO verify): Groq `openai/gpt-oss-20b` for profiler, flow analyst and critic (Groq retired the Llama 3.x self-serve models in Aug 2026); Gemini `gemini-3.8-flash` for the narrative. Both checked on the providers' model pages in Nov 2026.
- Live agents wrap their templates: the template computes the deterministic facts (and runs the bounded tool calls for the flow analyst; the LLM does not choose tools), then the LLM adds one cited assessment fact and a structured finding. Any `LLMUnavailable` returns the template output with `fallback_used=true`. In live mode, an agent whose provider has no key stays template.
- Narrative guards in code: evidence ids not in the ledger are dropped, uncited sentences are dropped, the risk score / typologies / disposition line / actions come from the template (so the stated disposition always equals the policy), the STR draft falls back to the template if any required section is missing, and a customer letter containing a tipping-off term is replaced by the neutral template.
- Cache key = sha256(model, prompt version, system, user); `_id` of `llm_cache` is the key (TTL 30 days). `node_executions.cache_hit` feeds the diagnostics cache hit rate.
- Prompts: `agents/prompts/<agent>.v1.md`; the version (file stem) is stamped on runs, node executions and cache keys. Run documents now take `prompt_versions` / `models` from the active agent suite.
- `uv run smoke --mode live` and `uv run evals --mode live --resume` pass the keys through; `LLM_MODE=live` in `.env` switches the API.
- CORS: `CORS_ORIGINS` (JSON list) already defaulted to `http://localhost:5173` and `http://127.0.0.1:5173`; now documented in `.env.example` with `VITE_API_URL`.

## Known gaps

- Live LLM calls are unverified against the real Groq and Gemini APIs (no keys). The request/response mapping follows the public API shapes; the first live smoke may need small fixes, which fall back to templates meanwhile.
- The flow analyst does not run an LLM-driven tool loop: the four read-only tools are called by code, and the LLM interprets the results.
- No separate token-bucket rate limiter: the semaphore of 2 plus backoff honouring `Retry-After` is the only quota protection. A full live eval may still need several `--resume` sessions.
- An earlier session of this clone had no `.env`, so `uv run dev` failed on the missing `MONGO_URI` and nothing could be checked against the live Atlas data. The UI types were checked against the backend code that builds each response, not against captured responses. Restore the `.env` and click through once.
- UI not built: light theme, keyboard shortcuts, Playwright, generated OpenAPI types (all skipped by instruction); the Audit explorer and Settings screens; PAN/account "reveal on click" (the API only ever returns masked values). The diagnostics cache hit rate shows "n/a" until the LLM cache exists.
- Sender cards show party type and count, not sender account age and KYC type, because the entity strip read model does not carry them for external parties.
- Separate reviewer gate (maker-checker for STR) skipped; one analyst gate only.
- Most API responses are plain dicts, not dedicated response models.
- SSE has no heartbeat; event history is in memory (a reconnect after an API restart only sees new events).
- Detector scans only the window ending at `as_of`, not a stepped rolling window. Organic alerts are 0, so detector precision on background noise is not really exercised.
- Existing pytest files from the earlier spec run are kept but were not run or updated in this phase; some will now be stale.
- mypy strict, ruff, CI and pre-commit were not run in this phase (by instruction).
- Audit chain lock is per process; two API processes could fork a case chain.
- Customer-facing tipping-off check is keyword based.
- About 590 counterparties instead of the target of 600.

## Commands (PowerShell, from the repo root)

```powershell
uv sync
uv run seed --seed 42 --customers 300 --reset   # generate + load + detect (~1 min on Atlas)
uv run seed --preview ACC-123456                 # one account's 14-day story
uv run check-policy                              # expected vs predicted for the 40 planted alerts
uv run smoke                                     # mule + seller through the graph, auto-approve
uv run evals --mode fallback                     # 40 alerts end to end; --resume to continue a run
uv run dev                                       # API on http://127.0.0.1:8000 (/health, /docs)
cd frontend; npm install; npm run dev            # UI on http://localhost:5173
```

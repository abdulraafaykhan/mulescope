# MuleScope

An AML triage copilot for one alert type: **mule accounts and rapid pass-through activity**.

A bank's detector flags an account that receives money from many senders and moves it out within minutes. MuleScope investigates the alert, scores it, recommends **Close**, **Escalate** or **STR Draft**, writes the narrative, and waits for an analyst to approve. Actions such as holds or KYC refresh are proposed, approved by a human, and executed as mock writes to the database.

The design rule: the investigation and the writing are separate from the decision. Metrics, the score and the recommended disposition are deterministic code. Agents explain and write; only an analyst can override the policy, and the reason is logged.

## Scope

**In scope:** mule and rapid pass-through alerts, alert detection, case queue, investigation graph (Profiler, Flow Analyst, Narrative Writer, Critic), deterministic scoring and disposition policy, action planning with a mock executor, analyst approval, tamper-evident audit trail, diagnostics, report export, evals.

**Out of scope:** card fraud, account takeover, phishing, sanctions screening, real-time blocking, real bank integrations and real customer data. All data in this project is synthetic.

## Architecture

```
                 React UI (Vite, :5173)
   queue · case workspace · money flow · agents · actions · audit · evals
                 |  REST /api/v1            ^  SSE /runs/{id}/stream
                 v                          |
+------------------------- FastAPI (:8000) ---------------------------+
|  api/routers (thin)  ->  services  ->  repositories (one per coll.) |
|                            |                                        |
|                            v                                        |
|   LangGraph case graph (compiled once, Mongo checkpointer)          |
|   load_case -> compute_metrics -> [profiler || flow_analyst]        |
|     -> aggregate_evidence -> sufficiency_check (max 1 loop)         |
|     -> score_and_policy -> plan_actions -> narrative_writer         |
|     -> critic (max 1 loop) -> analyst_gate [INTERRUPT]              |
|     -> apply_decision -> execute_actions (mock) -> finalize         |
|                                                                     |
|   domain/ (pure): metrics, signal registry, scoring, policy,        |
|                   typologies, action planner      <- config/*.yaml  |
+---------------------------------------------------------------------+
                 |                                   
                 v                                   
   MongoDB `mulescope` (operational)       MongoDB `mulescope_truth`
   accounts, transactions, alerts,         ground_truth only. Opened by
   cases, evidence, reports, actions,      `uv run seed` and `uv run evals`,
   audit_logs (hash chain), runs,          never by the API or agents.
   node_executions, eval_runs, ...
```

Every node is wrapped by one decorator that writes a `node_executions` row, appends an audit event to the case hash chain and publishes a live progress event. Runs pause at `analyst_gate` and resume on the analyst decision, also after an API restart.

## What works

- **Synthetic dataset**, seeded and reproducible: about 300 customers, 330 accounts, 590 counterparties and 50,000 ledger entries over 180 days. Indian context (en_IN names, VPAs, IFSC, UPI / IMPS / NEFT / RTGS / ATM / wallet), persona-driven behaviour, double-entry transfers and consistent running balances.
- **40 planted alerts** from five parametrised scenario classes (mule, seller, group collection, dormant, ambiguous), including a mule whose remarks try to instruct the AI reviewer. Labels live only in `mulescope_truth`.
- **Pass-through detector** over the 14-day window, thresholds in `config/scoring.yaml`, one alert and case per hit.
- **Deterministic policy**: 9 risk signals, 4 mitigators, score 0-100, typologies, disposition rules with a caution band and a victim-linked hard floor, playbook-driven actions.
- **Investigation graph** in LangGraph with parallel investigators, an `EVD-` evidence ledger, critic code checks (citations exist, disposition matches policy, STR sections present, no tipping-off words) and the analyst interrupt.
- **Analyst UI**: alert queue with KPIs and filters; case workspace with the sender / flagged account / receiver strip, score breakdown, evidence list, React Flow money-flow graph with a replay slider, timeline, virtualised transactions, report with EVD citation chips, live agent stepper over SSE, per-action approve / reject / reverse, audit log with hash-chain badge, diagnostics drawer and an account drawer; Evals page.
- **Eval harness**: `uv run evals --mode fallback|live` runs all 40 alerts end to end, resumable.

Agent text is generated from deterministic templates (`LLM_MODE=fallback`), so a run needs no LLM keys and takes about 3 seconds. Live Groq / Gemini agents are the next phase (see `PROGRESS.md`).

## Setup (PowerShell)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20.19+ or 22.12+ and a MongoDB 7 instance (Atlas, or local with `docker compose up -d` in `mulescope/`).

```powershell
cd mulescope
uv sync
Copy-Item .env.example .env      # set MONGO_URI and MONGO_TRUTH_URI; LLM keys may stay empty
cd frontend
npm install
Copy-Item .env.example .env.local   # VITE_API_URL=http://127.0.0.1:8000
```

The API allows the UI origin through `CORS_ORIGINS` (default `http://localhost:5173` and `http://127.0.0.1:5173`). The settings loader also reads a `.env` in the repository root.

## Run

From `mulescope/`, in three terminals:

```powershell
uv run seed --seed 42 --customers 300 --reset   # generate, load and detect (about a minute on Atlas)
uv run dev                                       # API at http://127.0.0.1:8000, docs at /docs
cd frontend; npm run dev                         # UI at http://localhost:5173
```

`--reset` drops both databases, including every case, run and audit log, so stop the API first.

In the UI: open a case from the queue, press **Start investigation**, watch the Agents panel, then review the money flow, report and actions and press **Approve** (or Edit, Override, Request more, Reject).

| Command | What it does |
| --- | --- |
| `uv run seed --seed 42 --customers 300 --reset` | Generate the dataset, load it, run the detector, print counts and any planted account without an alert |
| `uv run seed --preview ACC-123456` | Print one account's 14-day story |
| `uv run check-policy` | Expected vs predicted disposition for the 40 planted alerts (code only) |
| `uv run smoke` | One mule and one seller through the full graph with auto-approve |
| `uv run evals --mode fallback` | All 40 alerts through the graph; results on the Evals page |
| `uv run evals --mode live --resume` | Continue the latest unfinished live eval run, skipping evaluated cases |
| `uv run dev` | Start the API |

## Eval results

Policy version `policy-1.0.0`, graph `0.1.0`, dataset seed 42.

| Check | Result |
| --- | --- |
| Disposition accuracy, seed 42 (`uv run check-policy`) | 40 / 40 (100%) |
| Mules closed by mistake, seed 42 | 0 |
| Disposition accuracy, seed 7, no retuning | 40 / 40, 0 mules closed |
| Fallback graph runs (`uv run smoke`) | mule -> STR draft, seller -> Close, about 3 s each, audit chains valid |

**Read these numbers carefully.**

- The policy weights and thresholds in `config/scoring.yaml` were **tuned on the seed-42 planted alerts** (two of three allowed iterations). The seed-42 accuracy is **in-sample**.
- The seed-7 run used the same weights with no retuning. But seed 7 comes from the **same generator** with the same scenario definitions, so it is a synthetic-to-synthetic check, not evidence of performance on real bank data.
- **Known fragility:** three planted mules score **65, 65 and 68**. They are below the STR threshold of 70 and reach STR draft only through the near-threshold caution rule (score within 5 points of 70 with the STR conditions met). A small change in a weight or in the generated data could drop them to Escalate.

The full-graph eval (`uv run evals --mode fallback`) also measures citation validity, claim coverage, tipping-off violations, whether the injected-remark mule was obeyed, fallback rate, latency and tokens. It stores the results for the Evals page. It has not been run against the current dataset yet (see `PROGRESS.md`). Live-mode results will follow the live LLM phase.

## API overview

| Area | Endpoints |
| --- | --- |
| System | `GET /health`, `GET /api/v1/config/public` |
| Alerts | `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/detect` |
| Cases | `GET /cases`, `GET /cases/{id}`, `POST /cases/{id}/runs`, `POST /cases/{id}/decision` |
| Case data | `/cases/{id}/evidence`, `/report`, `/actions`, `/flow`, `/timeline`, `/transactions`, `/audit/verify` |
| Runs | `GET /runs/{run_id}/stream` (SSE), `GET /runs/{run_id}/diagnostics` |
| Accounts | `GET /accounts/{id}`, `GET /accounts/{id}/summary` |
| Actions | `PATCH /actions/{id}` (approve, reject, reverse) |
| Audit, evals | `GET /audit`, `GET /evals/runs`, `GET /evals/runs/{id}` |

## Repository layout

```
mulescope/
  backend/app/     api, services, graph, agents, domain, repositories, core
  datagen/         synthetic data generator and planted scenarios
  evals/           check-policy, smoke and the eval harness
  config/          scoring, playbook, scenario and LLM settings (YAML)
  frontend/        React + Vite + TypeScript analyst UI
docs/              BUILD_PROMPT.md, the specification
PROGRESS.md        build checklist, decisions and known gaps
```

## Known limits

The STR maker-checker reviewer gate is not built (one analyst gate). There is no light theme, no keyboard shortcuts and no Audit explorer or Settings screen. The SSE stream has no heartbeat, so the UI reconnects and refetches on a drop. The full list is in `PROGRESS.md`.

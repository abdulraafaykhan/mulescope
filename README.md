# MuleScope

An AML triage copilot for one alert type: **mule accounts and rapid pass-through activity**.

A bank's detector flags an account that receives money from many senders and moves it out within minutes. MuleScope investigates the alert, scores it, recommends **Close**, **Escalate** or **STR Draft**, writes the narrative, and waits for an analyst to approve.

The design rule is simple: the investigation and the writing are separate from the decision. Metrics, scores and the recommended disposition are computed by deterministic code. An analyst can override the recommendation, but only with a reason, and the override is logged.

## What is implemented

- **Synthetic dataset.** Seeded and reproducible: about 300 customers, 330 accounts, 590 counterparties and 50,000 ledger entries over 180 days. Indian context (names, VPAs, IFSC codes, UPI / IMPS / NEFT / RTGS / ATM / wallet channels), persona-based behaviour, double-entry transfers and consistent running balances.
- **40 planted alerts with hidden ground truth.** Mules, legitimate sellers, group collections, dormant accounts and ambiguous cases, including a mule whose transaction remarks try to instruct an AI reviewer. Ground truth lives in a separate database that the API never opens.
- **Pass-through detector.** Scans a 14-day window, applies thresholds from `config/scoring.yaml`, and creates an alert and a case for each hit.
- **Deterministic scoring and policy.** Flow metrics, nine risk signals, four mitigators, a score from 0 to 100, typology labels and a disposition policy. All weights and thresholds are configuration. On the 40 planted alerts the policy matches the expected disposition every time, and no mule is closed.
- **Investigation graph (LangGraph).** Profiler and Flow Analyst run in parallel, evidence is collected into a ledger with `EVD-` ids, then scoring, action planning, narrative and a critic check. The run pauses for the analyst, then resumes on their decision. Runs survive an API restart through a MongoDB checkpointer.
- **Analyst decisions and actions.** Approve, edit, override (reason required), request more evidence or reject. Proposed actions come from `config/playbook.yaml` and can be approved, rejected or reversed one by one. Execution is mocked by writing to the database.
- **Audit trail.** Every graph step is recorded, with a tamper-evident hash chain per case and a verify endpoint.
- **API.** Versioned REST under `/api/v1` plus a Server-Sent Events stream per run. The money-flow endpoint returns ready-to-render nodes and edges.

Agent text is currently generated from deterministic templates, so a run needs no LLM keys and takes about 3 seconds.

## How an investigation runs

```
load_case -> compute_metrics -> [ profiler || flow_analyst ] -> aggregate_evidence
   -> sufficiency_check (max 1 loop back to flow_analyst)
   -> score_and_policy -> plan_actions -> narrative_writer -> critic (max 1 loop)
   -> analyst_gate  [pauses for a human]
   -> apply_decision -> execute_actions (mock) -> finalize
```

## Tech stack

Python 3.12 and `uv`, FastAPI, Pydantic v2, LangGraph with `langgraph-checkpoint-mongodb`, MongoDB 7 (PyMongo async client), Faker (`en_IN`) and NumPy.

## Getting started

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and a MongoDB 7 instance (Atlas or local). All commands are PowerShell, run from `mulescope/`.

```powershell
cd mulescope
uv sync
Copy-Item .env.example .env      # then set MONGO_URI and MONGO_TRUTH_URI
uv run seed --seed 42 --customers 300 --reset
uv run dev
```

The settings loader also reads a `.env` in the repository root. The API starts at http://127.0.0.1:8000 and the interactive docs are at http://127.0.0.1:8000/docs.

`MONGO_TRUTH_URI` is only used by the seed and check commands. The API process never loads it.

### Commands

| Command | What it does |
| --- | --- |
| `uv run seed --seed 42 --customers 300 --reset` | Generates the dataset, loads it, runs the detector and prints counts and any planted account without an alert |
| `uv run seed --preview ACC-123456` | Prints one account's 14-day transaction story |
| `uv run check-policy` | Prints expected vs predicted disposition for the 40 planted alerts and the accuracy |
| `uv run smoke` | Runs one mule and one seller through the full graph and prints the outcome |
| `uv run dev` | Starts the API |

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
| Audit | `GET /audit` |

A quick way to try it: open `/docs`, call `GET /api/v1/cases`, pick a case with status `new`, start a run with `POST /cases/{id}/runs`, then read the evidence, report and actions and finish with `POST /cases/{id}/decision`.

## Repository layout

```
mulescope/
  backend/app/     api, services, graph, agents, domain logic, repositories, core
  datagen/         synthetic data generator and scenarios
  evals/           check-policy and smoke commands
  config/          scoring, playbook, scenario and LLM settings (YAML)
docs/              BUILD_PROMPT.md, the project specification
PROGRESS.md        current state of the build
```

## Scope

**In scope:** mule and rapid pass-through alerts, case queue, investigation, deterministic scoring and policy, action planning with a mock executor, analyst approval, audit trail and diagnostics.

**Out of scope:** card fraud, account takeover, phishing, sanctions screening, real-time blocking, real bank integrations and real customer data. All data in this project is synthetic.

# MuleScope backend

Backend, data generator and configuration for MuleScope. See the [repository README](../README.md) for the overview.

## Setup

Run everything in PowerShell from this directory. You need Python 3.12, `uv` and a MongoDB 7 instance (Atlas, or local with `docker compose up -d`).

```powershell
uv sync
Copy-Item .env.example .env
```

Set `MONGO_URI` and `MONGO_TRUTH_URI` in `.env`. They can point at the same cluster; the truth data uses a separate database name. The settings loader also reads a `.env` in the repository root, and real environment variables override both. Keys for Groq and Gemini can stay empty.

## Run

```powershell
uv run seed --seed 42 --customers 300 --reset   # generate, load and run the detector (about a minute on Atlas)
uv run check-policy                              # expected vs predicted disposition for the 40 planted alerts
uv run smoke                                     # one mule and one seller through the graph
uv run dev                                       # API at http://127.0.0.1:8000, docs at /docs
```

`uv run seed --reset` drops and recreates the `mulescope` and `mulescope_truth` databases, so stop the API first.

## Folders

| Folder | Contents |
| --- | --- |
| `backend/app/core` | settings, container, wiring, logging, errors, config loaders |
| `backend/app/domain` | enums, metrics, signals, scoring, disposition policy, action planner |
| `backend/app/repositories` | MongoDB access, one class per collection, collection setup |
| `backend/app/services` | detector, metrics, case runner, read models, action service |
| `backend/app/agents` | profiler, flow analyst, narrative writer, critic, read-only tools |
| `backend/app/graph` | state, nodes, edges, builder, checkpointer |
| `backend/app/api` | routers, schemas, error handling |
| `datagen` | personas, counterparties, ledger builder, scenarios, writers, validation |
| `evals` | `check-policy` and `smoke` commands |
| `config` | `scoring.yaml`, `playbook.yaml`, `scenarios.yaml`, `llm.yaml` |

## Configuration

Thresholds, weights, scenario parameters and action rules live in `config/*.yaml`, not in code. Changing a signal weight or a playbook rule needs no code change; rerun `uv run check-policy` to see the effect on the 40 planted alerts.

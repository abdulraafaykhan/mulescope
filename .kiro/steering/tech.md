---
inclusion: always
---

# Tech

## 2. Tech stack (final, do not substitute)

| Layer | Choice | Rule |
| --- | --- | --- |
| Language, packaging | Python 3.12, **uv** | Pin everything in `uv.lock`. Scripts in `pyproject.toml` (`uv run seed`, `uv run dev`, `uv run evals`). No Makefile, the dev machine is Windows. |
| Orchestration | **LangGraph** + `langgraph-checkpoint-mongodb` | Checkpoints in MongoDB with a TTL index (7 days). Compile the graph once at startup. |
| LLMs | **Groq** free tier (Profiler, Flow Analyst, Critic), **Gemini Flash** free tier (Narrative Writer) | Model names, limits and temperatures live in `config/llm.yaml`, never in code. |
| LLM access | Own `LLMProvider` interface | Retry with exponential backoff, a global concurrency semaphore, a token counter, and a **template fallback** so a quota error never breaks a case. |
| Backend | **FastAPI**, Pydantic v2, pydantic-settings | Fully async, typed, versioned routes under `/api/v1`. |
| DB driver | **PyMongo native async client** | Do not use Motor, it is deprecated. |
| Database | **MongoDB 7**: local Docker for development, Atlas M0 for the demo | Keep documents lean, the M0 limit is 512 MB. |
| Live updates | **Server-Sent Events** from LangGraph `astream` events | One stream per case run. |
| Frontend | **React, Vite, TypeScript**, Tailwind, shadcn/ui, TanStack Query | Strict TypeScript, no `any`. |
| Flow graph | **React Flow** + dagre | Custom account-card nodes. |
| Charts | Recharts |  |
| Synthetic data | Faker (`en_IN`), NumPy, seeded RNG | Same seed, same dataset, always. |
| Quality | pytest, pytest-asyncio, ruff, mypy, pre-commit, GitHub Actions | Tests run against a real local MongoDB, not mongomock. |
| Observability | Own `audit_logs` collection, optional LangSmith or Langfuse behind an env flag | The UI reads our own logs. |

**Deliberately not used:** vector DB or embeddings, pandas in request paths, Celery, Redis, sanctions screening. Typology knowledge is a versioned YAML playbook, so there is no embedding quota to worry about.

**Free-tier budget rules**

- Dataset size does not consume LLM quota. Only investigated alerts do, at about 15k tokens each across four LLM agents.
- A full 40-alert eval run is about 600k tokens. It must be resumable, rate-limit aware, and able to spread across several sessions or days.
- Cache every tool result and LLM response in a `llm_cache` collection keyed by a hash of the model, prompt version and input, so re-runs and tests cost nothing.
- Use the small model for routing and critique, and the larger one only for the narrative.
- Provide a `LLM_MODE=fallback` switch that runs the whole graph with deterministic template text. Use it for CI and demos.

## 10.2 Code standards

- Python 3.12 with full type hints. `mypy --strict` on `domain/`, `services/` and `graph/`. `ruff` for lint and format, enforced by pre-commit and CI.
- **Async all the way** for I/O. No blocking calls on the event loop.
- **No magic numbers or strings.** Thresholds, weights, model names, timeouts and limits come from `config/*.yaml` or settings. Enums for every closed set (status, disposition, channel, action type).
- Docstrings (Google style) on every public class and function: purpose, args, returns, raises. Comments explain **why** a decision was made, never what the line does.
- Small functions and classes, with early returns, and no deep nesting. Prefer composition over inheritance and pure functions in `domain/`.
- Logging: structured JSON through one logger factory, with `case_id` and `run_id` on every line. No `print`.
- Secrets only from environment variables. Ship `.env.example` with every variable (Mongo URIs for both databases, Groq and Gemini keys, `LLM_MODE`, `AS_OF_DATE`). Never commit keys.
- Frontend: strict TypeScript, ESLint and Prettier, no `any`, API types generated from OpenAPI, components under about 200 lines.
- **Git:** commit small and often. Write commit messages that are short, literal and plain, saying what actually changed, for example `add rapid exit signal` or `fix retention ratio when no inflow`. No polished or marketing-style wording.

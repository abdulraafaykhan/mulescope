# Requirements Document

## Introduction

This spec covers milestone **M0 (Scaffold)** of MuleScope, as defined in section 11 of the build prompt. M0 establishes the project skeleton and the operational foundations that every later milestone builds on: the repository layout, the `uv` Python project, local MongoDB via Docker, typed settings, a dependency-injection composition root, structured logging, a central error handler, collection bootstrapping (JSON Schema validators plus named indexes), continuous integration, and pre-commit.

The stack is fixed (build prompt section 2). No dependencies may be added beyond that section. All developer commands must run in PowerShell on Windows (no Makefile).

**M0 acceptance check (section 11):** `uv run dev` starts, `GET /health` is green, and all collections and indexes exist.

Out of scope for M0: synthetic data and the detector (M1), domain scoring logic (M2), repository method bodies and business routers (M3), the LangGraph graph (M4+), live LLM agents (M5), and the frontend application (M6+). M0 creates the directory placeholders and wiring points for these, but not their behaviour.

## Glossary

- **Operational database (`mulescope`):** the only database the API and agents connect to; holds alerts, cases, runs, evidence, reports, actions, audit logs, and the LLM cache.
- **Truth database (`mulescope_truth`):** holds planted ground truth; reachable only by `datagen` and `evals`, each through its own settings and connection string. The API process never loads a truth connection string.
- **API settings:** the settings object the FastAPI process loads; contains the operational `mulescope` connection only, with no `mongo_truth_uri`.
- **Datagen/evals settings:** separate settings objects, loaded only by the `datagen` and `evals` processes, that add the truth connection string.
- **Composition root:** `core/container.py`, which builds and injects repositories, services, LLM providers, and the compiled graph.
- **Bootstrapping:** `ensure_collections()` in `repositories/mongo/bootstrap.py`, which creates the operational collections with JSON Schema validators and named indexes at startup. `ensure_truth_collections()` separately creates the `ground_truth` collection in the truth database and is called only by `datagen`.
- **Checkpointer:** the LangGraph MongoDB checkpointer (`MongoDBSaver`) that owns the `checkpoints` and `checkpoint_writes` collections and manages their schema, indexes, and `created_at` TTL indexes when constructed with `ttl`.
- **Fallback mode:** `LLM_MODE=fallback`, a switch that runs the graph with deterministic template text and no LLM calls.

## Requirements

### Requirement 1: Repository layout and uv project

**User Story:** As a developer, I want the exact folder structure and a configured `uv` project, so that every later milestone has a predictable place to add code and reproducible commands to run it.

#### Acceptance Criteria

1. WHEN the repository is scaffolded THEN the system SHALL create the exact folder layout defined in section 4 under `mulescope/`, including `config/`, `backend/app/` (with `core`, `domain`, `repositories`, `services`, `agents`, `graph`, `llm`, `api` subtrees), `datagen/`, `evals/`, `tests/`, and `frontend/src/`.
2. WHEN a Python package directory is created THEN the system SHALL include a module docstring explaining the module's role and who calls it.
3. WHEN the project is initialised THEN the system SHALL define a `pyproject.toml` as a `uv` project that pins dependencies in `uv.lock` and declares the scripts `uv run seed`, `uv run dev`, and `uv run evals`, plus a lint script.
4. WHERE build tooling is concerned THE system SHALL NOT introduce a Makefile, because the dev machine is Windows.
5. WHEN dependencies are declared THEN the system SHALL include only the stack from section 2 and SHALL NOT add any dependency beyond it without a stated reason.
6. WHEN a command is documented or scripted THEN the system SHALL ensure it runs in PowerShell on Windows.
7. WHEN the repository is scaffolded THEN the system SHALL include a `.gitignore` covering Python, virtualenv, `uv`, environment files (`.env`), build artefacts, test and coverage output, editor and OS files, and frontend `node_modules` and build output.
8. WHEN the repository is scaffolded THEN the system SHALL include a `README.md` stub with the project name, a one-line description, the declared scope and out-of-scope list, and placeholder sections for setup, architecture, and eval results to be completed in later milestones.

### Requirement 2: Local MongoDB via Docker

**User Story:** As a developer, I want local MongoDB 7 running through Docker Compose, so that the app and tests run against a real database rather than a mock.

#### Acceptance Criteria

1. WHEN the developer starts the local environment THEN the system SHALL provide a `docker-compose.yml` that runs MongoDB 7 only.
2. WHEN the application connects to the database THEN the system SHALL use the PyMongo native async client and SHALL NOT use Motor.
3. WHEN the system models two logical databases THEN the system SHALL connect the API and agents only to the operational `mulescope` database, and SHALL keep the `mulescope_truth` database reachable only by `datagen` and `evals` through their own settings and connection string.
4. WHEN the connection is established THEN the system SHALL create the connection pool once at startup rather than per request.
5. WHEN the checkpointer is constructed THEN the system SHALL give it a dedicated synchronous PyMongo `MongoClient` created once at startup, separate from the async operational client, because the library accepts only a sync client; this is the only sync client in the API process.

### Requirement 3: Typed settings and secrets

**User Story:** As a developer, I want typed configuration loaded from the environment and YAML, so that no magic numbers, strings, or secrets live in code and the API process cannot reach the truth database.

#### Acceptance Criteria

1. WHEN settings are loaded THEN the system SHALL use pydantic-settings to read configuration, with full type hints.
2. WHEN the API process loads its settings THEN the system SHALL expose only the operational `mulescope` connection and SHALL NOT include a `mongo_truth_uri` field, so the API has no way to reach the truth database.
3. WHEN `datagen` or `evals` loads settings THEN the system SHALL load a separate settings object that adds the truth database connection string, kept out of the API settings.
4. WHEN a secret is required THEN the system SHALL read it only from environment variables and SHALL NOT commit keys.
5. WHEN the project ships THEN the system SHALL provide a `.env.example` listing every variable, including the operational Mongo URI, the truth Mongo URI (used only by datagen and evals), Groq and Gemini keys, `LLM_MODE`, and `AS_OF_DATE`.
6. WHEN configuration values such as thresholds, weights, model names, timeouts, or limits are needed THEN the system SHALL source them from `config/*.yaml` or settings, never as literals in code.
7. WHEN `config/` is scaffolded THEN the system SHALL create placeholder `llm.yaml`, `scoring.yaml`, `playbook.yaml`, and `scenarios.yaml` files.

### Requirement 4: Composition root and dependency injection

**User Story:** As a developer, I want a single composition root that builds and injects dependencies, so that services and nodes receive their collaborators explicitly and the architecture stays layered.

#### Acceptance Criteria

1. WHEN the application assembles its dependencies THEN the system SHALL build repositories, services, LLM providers, and the compiled graph in `core/container.py` and inject them with FastAPI `Depends`.
2. WHERE dependencies flow between layers THE system SHALL point dependencies inward only: controllers call services, services call repositories and agents, and nothing in `domain` imports FastAPI, PyMongo, or LangGraph.
3. WHEN a service or graph node needs a collaborator THEN the system SHALL pass it through a constructor or `RunnableConfig`, with no global clients and no `import db` inside a node.
4. WHEN dependencies are declared THEN the system SHALL depend on small, segregated interfaces so that a consumer depends only on the ports it uses.

### Requirement 5: FastAPI application factory and health endpoint

**User Story:** As a developer, I want a FastAPI app with a lifespan and a health route, so that I can confirm the service starts and its dependencies are reachable.

#### Acceptance Criteria

1. WHEN the application starts THEN the system SHALL expose a FastAPI app factory in `backend/app/main.py` with a lifespan that opens the Mongo connection, runs collection bootstrapping, and compiles the graph once at startup.
2. WHEN a client calls `GET /health` THEN the system SHALL serve it at the root path `/health` (not under `/api/v1`) and return a green/healthy response.
3. WHEN business and system routes other than health are mounted THEN the system SHALL version them under `/api/v1` and keep controllers thin (validate, call one service, return a schema, no business logic).
4. WHEN the developer runs `uv run dev` THEN the system SHALL start the API successfully.
5. WHEN a client calls `GET /api/v1/config/public` THEN the system SHALL return the LLM mode, versions, and provider status.
6. WHEN the app handles requests and responses THEN the system SHALL be fully async and typed, with no blocking calls on the event loop.

### Requirement 6: Collection bootstrapping with validators and indexes

**User Story:** As a developer, I want all collections created with JSON Schema validators and named indexes at startup, so that the data model is enforced and queries are backed by the right indexes from day one.

#### Acceptance Criteria

1. WHEN the application starts THEN the system SHALL run `ensure_collections()` in `repositories/mongo/bootstrap.py` to create every operational collection with its JSON Schema validator and its named indexes.
2. WHEN each operational collection is created THEN the system SHALL create it with the indexes listed in section 5, for example `accounts` unique `account_no` and unique `vpa`, `transactions` `(account_id, ts)` and `(counterparty.ref_id, ts)` and `transfer_id`, `alerts` unique `dedupe_key` and `(status, priority)` and `account_id`, `cases` unique `alert_id`, and `llm_cache` unique `key` with a 30-day TTL.
3. WHEN each validator is defined THEN the system SHALL enforce the correct `_id` type per collection: a prefixed-string pattern for business entities (`customers` `CUS-`, `accounts` `ACC-`, `alerts` `ALT-`, `cases` `CASE-`, `evidence` `EVD-`, `actions` `ACT-`, and the corresponding prefixes for `counterparties`, `users`, `complaints`), and `ObjectId` for high-volume or append-only collections (`transactions`, `audit_logs`, `node_executions`).
4. WHEN the collections used by M1 are bootstrapped THEN the system SHALL define full JSON Schema validators (required fields and field types, not only a baseline) for `customers`, `accounts`, `counterparties`, `transactions`, `complaints`, `alerts`, and `dataset_meta`, consistent with section 5.
5. WHEN the checkpointer is constructed THEN the system SHALL create it with `ttl` set from configuration to 7 days (the retention value sourced from settings or `config/*.yaml` per Requirement 3.6, not a literal in code), so the checkpointer itself creates the `created_at` TTL indexes on `checkpoints` and `checkpoint_writes`; the system SHALL treat both collections as owned by the checkpointer and SHALL NOT create indexes on or write to them from its own bootstrap.
6. WHEN documents are modelled THEN the system SHALL follow the section 5 conventions: `snake_case` fields, readable prefixed string `_id` for business entities and `ObjectId` for high-volume or append-only data, Decimal128 INR money, UTC `datetime`, and `created_at` on every document with `updated_at` and `schema_version` on mutable ones.
7. WHEN the truth database is seeded THEN the system SHALL provide `ensure_truth_collections()` that creates the `ground_truth` collection with its validator and indexes in the `mulescope_truth` database, and this function SHALL be called only by `datagen`, never during API startup.
8. WHEN bootstrapping runs more than once THEN the system SHALL be idempotent, leaving existing collections and indexes intact.

### Requirement 7: Structured logging and central error handling

**User Story:** As a developer, I want structured JSON logging and one error handler, so that every log line is traceable and domain errors map consistently to HTTP responses.

#### Acceptance Criteria

1. WHEN any component logs THEN the system SHALL emit structured JSON through a single logger factory and SHALL NOT use `print`.
2. WHEN a log line is written within a case or run THEN the system SHALL include `case_id` and `run_id` on the line.
3. WHEN the domain raises an error THEN the system SHALL define the exception hierarchy `DomainError`, `NotFound`, `PolicyViolation`, `LLMUnavailable`, and `DependencyUnavailable` (infrastructure failures such as an unreachable database).
4. WHEN an error reaches the API boundary THEN the system SHALL map it to an HTTP status in one handler and return the consistent error envelope, including mapping `DependencyUnavailable` to 503.

### Requirement 8: Quality gates with CI and pre-commit

**User Story:** As a developer, I want lint, type checks, and tests enforced by pre-commit and CI, so that quality standards hold from the first commit.

#### Acceptance Criteria

1. WHEN code is committed THEN the system SHALL run `ruff` for lint and format via pre-commit.
2. WHEN type checking runs THEN the system SHALL run `mypy --strict` on `domain/`, `services/`, and `graph/`.
3. WHEN CI runs THEN the system SHALL execute lint, type checks, and tests through GitHub Actions, with tests running against a real local MongoDB rather than mongomock.
4. WHEN a milestone is declared done THEN the system SHALL have run lint, type checks, and tests and SHALL report the real results, including failures.
5. WHERE the frontend is concerned THE system SHALL NOT scaffold frontend tooling in M0; strict TypeScript, ESLint, and Prettier with no `any` arrive with the frontend in M6.

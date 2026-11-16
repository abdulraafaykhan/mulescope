# Implementation Plan: M0 Scaffold

## Overview

Build the MuleScope scaffold in Python 3.12 under `mulescope/`, exactly as laid out in structure.md section 4. Work bottom-up: project tooling and root files, then `core/` (settings, clock, logging, errors), domain enums, collection bootstrapping, the composition root with the checkpointer and placeholder graph, the API (root `/health`, `/api/v1/config/public`, one error handler), the `seed`/`evals` stubs, and the quality gates. Each step is wired into the previous ones, so nothing is left orphaned. The last step checks the M0 acceptance criteria and updates `PROGRESS.md`.

Every command must run in PowerShell on Windows. Use `uv sync`, `uv run ...` and `docker compose up -d`. Do not use a Makefile, `&&`-chained scripts, `export` or other bash-only syntax. Set environment variables in PowerShell with `$env:NAME = "value"`.

Dependencies are restricted to the section 2 stack. The full list is in task 1.1, and every item outside the core list has a stated reason.

## Tasks

- [x] 1. Set up the repository skeleton and project tooling
  - [x] 1.1 Create `mulescope/pyproject.toml` as a `uv` project and generate `uv.lock`
    - `requires-python = ">=3.12,<3.13"`, project name `mulescope`. Make `backend`, `datagen` and `evals` importable as packages from the `mulescope/` root, for example `backend.app.main`.
    - Runtime dependencies:
      - `fastapi`
      - `uvicorn`, the ASGI server FastAPI needs to run. It is required by `uv run dev` because FastAPI itself has no server.
      - `pydantic` v2 and `pydantic-settings`
      - `pymongo`, using the native `AsyncMongoClient`. Pin a version that has the async API. Do NOT add Motor.
      - `langgraph` and `langgraph-checkpoint-mongodb`
      - `pyyaml`. Reason: section 10.2 requires thresholds, model names and limits to live in `config/*.yaml`, and the stdlib has no YAML parser.
    - Dev dependency group:
      - `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `pre-commit`
      - `httpx`. Reason: FastAPI's `TestClient` and `httpx.ASGITransport` need it, and it is NOT a transitive dependency of plain `fastapi`. It is dev-only and never imported by app code. Flag this to the user when the task is done.
      - Do NOT add Faker or NumPy (M1), Hypothesis, mongomock or Motor.
    - Scripts in `[project.scripts]`:
      - `dev = "backend.app.main:run"`
      - `seed = "datagen.cli:main"`
      - `evals = "evals.cli:main"`
      - `lint = "backend.app.lint:main"`, a small Python runner that calls `ruff check`, `ruff format --check` and `mypy` through `subprocess` with list arguments, so it works in PowerShell with no shell chaining
    - Tool config sections:
      - `[tool.ruff]`: target py312, line length, rule sets
      - `[tool.mypy]`: `strict = true` with `files` set to `backend/app/domain`, `backend/app/services` and `backend/app/graph`
      - `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, and markers `unit` and `integration`
    - Run `uv lock` and `uv sync` in PowerShell from `mulescope/` and commit `uv.lock`.
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 2.2, 8.2_

  - [x] 1.2 Create the full section-4 directory tree with module docstrings
    - Create `__init__.py` in every Python package. Each one gets a module docstring that states the module's role and who calls it. The packages are:
      - `backend/`, `backend/app/` and the `core`, `domain` (with `entities`, `signals`, `policy`), `repositories` (with `interfaces`, `mongo`), `services`, `agents` (with `prompts`, `tools`), `graph` (with `nodes`), `llm` and `api` (with `routers`, `schemas`) subpackages
      - `datagen/` (with `factories`, `scenarios`), `evals/`, and `tests/` (with `unit`, `integration`)
    - Create the `frontend/src/` subdirectories (`app`, `features`, `components/ui`, `lib`, `styles`, `types`), each with only a `.gitkeep`. Add no frontend tooling, `package.json`, TS, ESLint or Prettier config.
    - _Requirements: 1.1, 1.2, 8.5_

  - [x] 1.3 Create `mulescope/.gitignore` and the `mulescope/README.md` stub
    - `.gitignore` covers:
      - `__pycache__/` and `*.pyc`
      - `.venv/` and uv caches
      - `.env` and `.env.*`, but keeps `.env.example`
      - `build/`, `dist/` and `*.egg-info`
      - `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage` and `htmlcov/`
      - `.idea/`, local `.vscode/` and `.DS_Store`/`Thumbs.db`
      - `frontend/node_modules/` and `frontend/dist/`
    - README contents:
      - project name and a one-line description
      - the in-scope and out-of-scope lists from section 1
      - placeholder sections for Setup (PowerShell commands), Architecture and Eval results
    - _Requirements: 1.6, 1.7, 1.8_

  - [x] 1.4 Create `mulescope/docker-compose.yml` and `mulescope/.env.example`
    - Compose runs a single `mongo:7` service. It has a named volume, exposes port 27017 and has a `mongosh` ping healthcheck. No other services.
    - `.env.example` lists every settings variable with safe placeholder values and no real keys:
      - `MONGO_URI` and `MONGO_DB_NAME`
      - `MONGO_TRUTH_URI` and `MONGO_TRUTH_DB_NAME`, with a comment that only datagen and evals use them
      - `GROQ_API_KEY` and `GEMINI_API_KEY`
      - `LLM_MODE`, `AS_OF_DATE` and `CHECKPOINT_TTL_DAYS=7`
      - `MONGO_SERVER_SELECTION_TIMEOUT_MS`, `API_HOST` and `API_PORT`
    - _Requirements: 2.1, 3.4, 3.5, 1.6_

  - [x] 1.5 Create placeholder `mulescope/config/llm.yaml`, `scoring.yaml`, `playbook.yaml` and `scenarios.yaml`
    - Use commented skeletons with `TODO verify` notes where regulatory values will live later.
    - `llm.yaml` carries a `version` key, per-agent model name and temperature placeholders, and `cache.ttl_days: 30`, which is the source of the `llm_cache` TTL.
    - `scoring.yaml`, `playbook.yaml` and `scenarios.yaml` each carry a `version` key and empty sections.
    - _Requirements: 3.6, 3.7_

- [x] 2. Implement core: settings, config loader, clock, logging and errors
  - [x] 2.1 Implement `backend/app/core/settings.py`
    - `BaseAppSettings(BaseSettings)` has these fully typed fields:
      - `mongo_uri`
      - `mongo_db_name`, default `mulescope`
      - `groq_api_key` and `gemini_api_key`, both `str | None`
      - `llm_mode: LlmMode`, default `fallback`
      - `as_of_date: date`
      - `graph_version`
      - `checkpoint_ttl_days: int`, default 7
      - `mongo_server_selection_timeout_ms`
      - `config_dir`
    - It also has a derived `checkpoint_ttl_seconds` property. Settings are read from env and `.env`.
    - `ApiSettings(BaseAppSettings)` adds `api_host` and `api_port`, and has NO `mongo_truth_uri` field.
    - `DatagenSettings` and `EvalsSettings` each add `mongo_truth_uri` and `mongo_truth_db_name` (default `mulescope_truth`).
    - Google-style docstrings throughout. Secrets come only from env.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 2.3, 6.5_

  - [x] 2.2 Implement `backend/app/core/config_files.py`
    - Write a typed loader for `config/*.yaml`. It uses `yaml.safe_load` and validates into small Pydantic models. In M0 that is `LlmConfig`, which exposes `version`, the provider/model placeholders and `cache_ttl_seconds` derived from `cache.ttl_days`.
    - Raise `DependencyUnavailable` with a clear message when a file is missing or invalid.
    - _Requirements: 3.6, 3.7_

  - [x] 2.3 Implement `backend/app/core/clock.py`
    - Write a `Clock` protocol and a `SystemClock` that returns timezone-aware UTC `datetime`. This is the single time source, so nothing calls `datetime.now()` directly.
    - _Requirements: 6.6_

  - [x] 2.4 Implement `backend/app/core/logging.py`
    - Write one `get_logger(name)` factory with a stdlib `logging` JSON formatter. Do not add a library for this.
    - `contextvars` carry `case_id` and `run_id`, and a `bind_run_context(case_id, run_id)` context manager sets them. Every line includes both keys, set to `null` when unset.
    - Write a `configure_logging(level)` entry point.
    - Do not use `print` anywhere.
    - _Requirements: 7.1, 7.2_

  - [x] 2.5 Implement `backend/app/core/errors.py`
    - Define `DomainError` and its subclasses `NotFound`, `PolicyViolation`, `LLMUnavailable` and `DependencyUnavailable`.
    - Each carries `message` and an optional `detail`. There is no HTTP knowledge here, because the mapping lives in the API layer.
    - _Requirements: 7.3_

  - [x]* 2.6 Write unit tests for settings, logging and errors
    - `tests/unit/test_settings.py`:
      - `ApiSettings` has no `mongo_truth_uri` in `model_fields`, but `DatagenSettings` and `EvalsSettings` do
      - `checkpoint_ttl_seconds == checkpoint_ttl_days * 86400`
      - env values override defaults
    - `tests/unit/test_logging.py`: every emitted line parses as JSON and carries `case_id` and `run_id` inside and outside `bind_run_context`.
    - `tests/unit/test_config_files.py`: `LlmConfig` loads the placeholder YAML, and a missing file raises `DependencyUnavailable`.
    - **Property 7: Truth isolation by construction (settings part)**
    - **Validates: Requirements 3.1, 3.2, 3.3, 7.1, 7.2**

  - [x]* 2.7 Write property test for no secrets in code
    - **Property 8: No secrets in code**
    - `tests/unit/test_no_secrets.py`:
      - scans every `.py` under `backend/`, `datagen/` and `evals/` for API-key-shaped literals, such as `gsk_` or `AIza` prefixes and long assignments to `*_api_key`
      - asserts that every env-backed field across all four settings classes appears in `.env.example`
    - **Validates: Requirements 3.4, 3.5**

  - [x]* 2.8 Write property test for config sourcing
    - **Property 9: Config sourcing**
    - `tests/unit/test_config_sourcing.py` walks the AST of every module in `domain/`, `services/` and `graph/`. It asserts there are no numeric literals other than an allow-list (0, 1, -1), and no string literals that look like model names or durations outside docstrings and enum definitions.
    - **Validates: Requirements 3.6**

- [x] 3. Implement domain enums
  - [x] 3.1 Implement `backend/app/domain/enums.py`
    - Define `LlmMode(StrEnum)` with `live` and `fallback`.
    - Add stub `StrEnum`s for the closed sets later milestones extend: `Disposition`, `Channel`, `ActionType`, `AlertStatus` and `CaseStatus`.
    - Add `IdPrefix(StrEnum)` with the business-entity `_id` prefixes `CUS-`, `ACC-`, `CPY-`, `CMP-`, `USR-`, `ALT-`, `CASE-`, `RUN-`, `EVD-`, `RPT-`, `ACT-` and `DEC-`.
    - Imports are restricted to stdlib and pydantic.
    - _Requirements: 4.2, 6.3, 6.6_

  - [x]* 3.2 Write property test for layer isolation
    - **Property 1: Layer isolation**
    - `tests/unit/test_domain_import_guard.py` enumerates every module under `backend/app/domain` with `pkgutil.walk_packages`.
    - For each module it runs `python -c "import <module>; import sys; ..."` in a fresh subprocess, using `sys.executable` and list arguments so it is PowerShell-safe. It asserts that no `fastapi*`, `pymongo*` or `langgraph*` key is in `sys.modules`.
    - **Validates: Requirements 4.2**

- [x] 4. Implement collection bootstrapping
  - [x] 4.1 Implement `backend/app/repositories/mongo/validators.py`
    - Write `$jsonSchema` validators per collection.
    - `_id` rule:
      - prefixed-string `pattern` built from `IdPrefix` for `customers`, `accounts`, `counterparties`, `complaints`, `users`, `alerts`, `cases`, `case_runs`, `evidence`, `reports`, `actions` and `decisions`
      - `bsonType: objectId` for `transactions`, `audit_logs` and `node_executions`
      - plain string for `llm_cache`, `eval_runs`, `eval_results`, `dataset_meta` and `ground_truth`
    - Full validators (required fields and `bsonType`s) for `customers`, `accounts`, `counterparties`, `transactions`, `complaints`, `alerts` and `dataset_meta`, consistent with section 5:
      - money is `decimal`, times are `date`, and all fields are `snake_case`
      - every document requires `created_at`
      - mutable entities require `updated_at` and `schema_version`
    - Baseline validators (`_id` type and required `created_at`) for the remaining operational collections.
    - Split the file if it grows past about 250 lines, for example into `validators_m1.py` and `validators_baseline.py`.
    - _Requirements: 6.3, 6.4, 6.6_

  - [x] 4.2 Implement `backend/app/repositories/mongo/index_plan.py`
    - Write a typed, declarative list of `IndexSpec(collection, name, keys, unique, ttl_seconds)` covering every named index in the design's collection and index plan.
    - The plan includes:
      - `accounts`: unique `account_no` and unique `vpa`
      - `transactions`: `(account_id, ts)`, `(counterparty.ref_id, ts)` and `transfer_id`
      - `alerts`: unique `dedupe_key`, `(status, priority)` and `account_id`
      - `cases`: unique `alert_id`
      - `llm_cache`: unique `key`, plus a `created_at` TTL whose seconds are passed in from `LlmConfig.cache_ttl_seconds` and are not a literal
    - A separate truth plan covers `ground_truth` `account_id` and `scenario_type`.
    - There are NO entries for `checkpoints` or `checkpoint_writes`.
    - _Requirements: 6.2, 6.5, 6.7, 3.6_

  - [x] 4.3 Implement `backend/app/repositories/mongo/bootstrap.py`
    - `async def ensure_collections(db: AsyncDatabase, llm_cache_ttl_seconds: int) -> None`:
      - creates each missing collection with its validator
      - applies `collMod` to refresh the validator on existing collections
      - creates every named index from the plan, idempotently
      - logs one structured line per collection
    - `async def ensure_truth_collections(truth_db: AsyncDatabase) -> None` does the same for `ground_truth`. Its docstring states that only `datagen` may call it.
    - Raise `DependencyUnavailable` on connection failure.
    - Never touch `checkpoints` or `checkpoint_writes`.
    - _Requirements: 6.1, 6.2, 6.5, 6.7, 6.8, 5.6_

  - [x] 4.4 Implement `tests/conftest.py` against a real local MongoDB
    - Build test settings from env, defaulting to `mongodb://localhost:27017`.
    - Give each test module a unique test database name (`mulescope_test_<uuid>`) and a truth test database (`mulescope_truth_test_<uuid>`). Drop both after the module.
    - Provide async fixtures for the async client and the database handle.
    - Fail with a clear message telling the user to run `docker compose up -d` when Mongo is unreachable. Do not skip silently and do not use mongomock.
    - _Requirements: 8.3_

  - [x]* 4.5 Write property test for bootstrap idempotency
    - **Property 2: Bootstrap idempotency**
    - `tests/integration/test_bootstrap_idempotency.py` runs `ensure_collections` 1, 2 and 3 times, using parametrize, on a fresh test database.
    - It asserts that the collection names and the `index_information()` of every collection are identical across runs, that there are no errors, and that there are no duplicate indexes. A pre-existing collection created without a validator gets the validator applied.
    - **Validates: Requirements 6.1, 6.8**

  - [x]* 4.6 Write property test for index and validator completeness
    - **Property 3: Index and validator completeness (bootstrap part)**
    - `tests/integration/test_bootstrap_indexes.py`, parametrized over every `IndexSpec`, asserts that each named index exists with the right keys and `unique` flag. It also asserts that `llm_cache` `created_at` has `expireAfterSeconds` equal to the configured value.
    - Parametrized over every collection, it inserts a document with a wrong-typed `_id` (string versus ObjectId, wrong prefix) and asserts the insert is rejected.
    - It asserts that `checkpoints` and `checkpoint_writes` have no indexes created by `ensure_collections` alone.
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.5**

  - [x]* 4.7 Write integration tests for the full M1 validators
    - `tests/integration/test_m1_validators.py`: for each of `customers`, `accounts`, `counterparties`, `transactions`, `complaints`, `alerts` and `dataset_meta`, a valid document is accepted.
    - Variants are rejected when a required field is missing, when money is a float instead of a `Decimal128`, and when a time is a string instead of a `datetime`.
    - **Validates: Requirements 6.4, 6.6**

- [ ] 5. Checkpoint: run lint, type checks and tests
  - Run `docker compose up -d`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run pytest`. Report the real results, including failures. Ensure all tests pass, and ask the user if questions arise.
  - _Requirements: 8.4_

- [ ] 6. Implement the graph wiring, health port, services and composition root
  - [x] 6.1 Implement `backend/app/graph/checkpoint.py` and `backend/app/graph/builder.py`
    - `build_checkpointer(sync_client: MongoClient, db_name: str, ttl_seconds: int) -> MongoDBSaver` returns `MongoDBSaver(client=..., db_name=..., ttl=ttl_seconds)`. Its docstring says the saver owns the `checkpoints` and `checkpoint_writes` collections and their TTL indexes.
    - `build_graph(checkpointer) -> CompiledStateGraph` compiles a trivial placeholder `StateGraph` with a typed state and a single pass-through node. Real nodes arrive in M4.
    - Both must pass `mypy --strict`.
    - _Requirements: 2.5, 5.1, 6.5_

  - [x] 6.2 Implement the health port and the system service
    - `backend/app/repositories/interfaces/health_probe.py` defines a small `HealthProbe` protocol with `async ping() -> None`.
    - `backend/app/repositories/mongo/health_probe.py` defines `MongoHealthProbe(db)`, which runs the `ping` command and raises `DependencyUnavailable` on failure.
    - `backend/app/services/system_service.py` defines `SystemService(probe, settings_view)`:
      - `async check_health()` returns a typed result
      - `public_config()` returns the LLM mode, `graph_version`, config versions and provider status (key configured or not, and fallback active). It never exposes key values.
    - _Requirements: 4.2, 4.3, 4.4, 5.2, 5.5_

  - [ ] 6.3 Implement `backend/app/core/container.py`
    - `Container(settings: ApiSettings, llm_config: LlmConfig)` has these members:
      - `async startup()`:
        - creates the single `AsyncMongoClient` with the pool once and the timeout from settings
        - resolves the `mulescope` handle
        - calls `ensure_collections(db, llm_config.cache_ttl_seconds)`
        - creates the sync `MongoClient` and calls `build_checkpointer(..., settings.checkpoint_ttl_seconds)` through `asyncio.to_thread`
        - compiles the placeholder graph once
        - builds `MongoHealthProbe` and `SystemService`
      - the `db`, `checkpointer`, `graph` and `system_service` properties, which raise if accessed before startup
      - `async shutdown()`, which closes the async client and the sync client off-loop
    - The container holds no truth handle and never imports `ensure_truth_collections`.
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 4.1, 4.3, 5.1, 5.6, 6.1, 6.5_

  - [ ]* 6.4 Write property test for client ownership
    - **Property 4: Client ownership**
    - `tests/integration/test_container_clients.py` patches the `AsyncMongoClient` and `MongoClient` constructors with counting wrappers that delegate to the real classes. It runs `startup()` and asserts exactly one of each.
    - It asserts that the sync client is referenced only by the checkpointer, that `shutdown()` closes both, and that repeated `system_service` access constructs no new client.
    - It asserts that `bootstrap.py` contains no reference to `checkpoints` or `checkpoint_writes`.
    - **Validates: Requirements 2.4, 2.5, 4.3, 6.5**

- [ ] 7. Implement the API layer and the app factory
  - [ ] 7.1 Implement the API schemas
    - `backend/app/api/schemas/system.py` holds `HealthResponse(status, db)` and `PublicConfigResponse(llm_mode, graph_version, config_versions, providers)`.
    - `backend/app/api/schemas/errors.py` holds `ErrorBody(code, message, detail)` and `ErrorEnvelope(error)`.
    - _Requirements: 5.2, 5.5, 7.4_

  - [ ] 7.2 Implement `backend/app/api/error_handlers.py`
    - Write a single `register_error_handlers(app)` with a mapping table:
      - `NotFound`: 404 `not_found`
      - `PolicyViolation`: 409 `policy_violation`
      - `LLMUnavailable`: 503 `llm_unavailable`
      - `DependencyUnavailable`: 503 `dependency_unavailable`
      - `DomainError`: 400 `domain_error`
      - unhandled: 500 `internal_error`
    - Resolve by walking the MRO so subclasses map correctly.
    - Log one structured line per handled error, with `case_id` and `run_id` when bound.
    - _Requirements: 7.3, 7.4, 7.1, 7.2_

  - [ ] 7.3 Implement `backend/app/api/deps.py`
    - Write thin `Depends` providers: `get_container(request)`, which reads `app.state.container`, and `get_system_service`. Nothing is constructed per request.
    - _Requirements: 4.1, 4.3_

  - [ ] 7.4 Implement the routers
    - `backend/app/api/routers/health.py` serves `GET /health` at the root. It calls `SystemService.check_health()` and returns `HealthResponse`. A failed ping raises `DependencyUnavailable`, which becomes 503 through the handler.
    - `backend/app/api/routers/config.py` serves `GET /config/public` and is mounted under `/api/v1`.
    - Placeholder modules `alerts.py`, `cases.py`, `accounts.py`, `actions.py`, `audit.py`, `evals.py` and `stream.py` each contain a docstring and an empty `APIRouter`, with no endpoints yet.
    - _Requirements: 5.2, 5.3, 5.5, 5.6_

  - [ ] 7.5 Implement `backend/app/main.py`
    - `create_app(settings: ApiSettings | None = None) -> FastAPI`:
      - an async lifespan builds the `Container` from `ApiSettings` and `LlmConfig`, calls `startup()`, stores it on `app.state`, yields, then calls `shutdown()`
      - registers the error handlers
      - mounts the health router at the root and the other routers under `/api/v1`
      - calls `configure_logging`
    - `run()` is the `uv run dev` entry. It calls `uvicorn.run("backend.app.main:create_app", factory=True, host=settings.api_host, port=settings.api_port)`.
    - The API startup path never calls `ensure_truth_collections`.
    - _Requirements: 5.1, 5.3, 5.4, 5.6, 2.3, 6.7_

  - [ ]* 7.6 Write property test for error envelope totality
    - **Property 5: Error envelope totality**
    - `tests/unit/test_error_envelope.py` is parametrized over every subclass of `DomainError`, found recursively with `__subclasses__()`, plus a test-local ad-hoc subclass. It mounts a throwaway route that raises the subclass on a minimal app with `register_error_handlers`.
    - It asserts a defined non-500 status, the exact envelope shape, `DependencyUnavailable` mapping to 503, and an unhandled `RuntimeError` producing 500 `internal_error`.
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 7.7 Write property test for health truthfulness and placement
    - **Property 6: Health truthfulness and placement**
    - `tests/integration/test_health.py` uses `TestClient(create_app(test_settings))` against live Mongo.
    - It asserts that `GET /health` returns 200 with `db: ok` and that `GET /api/v1/health` returns 404.
    - It overrides the `get_system_service` dependency with a `SystemService` whose `MongoHealthProbe` points at an unreachable URI with a short timeout from settings. It asserts 503 with `dependency_unavailable` and never a 200.
    - **Validates: Requirements 5.2, 5.4**

  - [ ]* 7.8 Write integration tests for public config, the checkpointer TTL and startup truth isolation
    - `tests/integration/test_config_public.py`: `GET /api/v1/config/public` returns the configured `llm_mode`, `graph_version`, config versions and provider status, and no key values.
    - `tests/integration/test_checkpointer_ttl.py`: after app startup, both `checkpoints` and `checkpoint_writes` have a `created_at` TTL index with `expireAfterSeconds == settings.checkpoint_ttl_seconds` (**Property 3**, checkpointer part).
    - `tests/integration/test_startup_truth_isolation.py`: patch `ensure_truth_collections` to fail if it is called, start the app, and assert it was never called and that the container exposes no truth handle (**Property 7**, runtime part).
    - **Validates: Requirements 5.5, 6.5, 2.3, 3.2, 6.7**

- [ ] 8. Implement the `seed` and `evals` stub entry points
  - [ ] 8.1 Implement `datagen/cli.py` with `main()`
    - Load `DatagenSettings`, open the truth database with its own client, call `ensure_truth_collections(truth_db)`, close the client, then log through `get_logger` (not `print`) that data generation arrives in M1.
    - This is the only caller of `ensure_truth_collections`.
    - Use `asyncio.run` for the async work.
    - _Requirements: 3.3, 6.7, 7.1, 1.3_

  - [ ] 8.2 Implement `evals/cli.py` with `main()`
    - Load `EvalsSettings` and log through `get_logger` that evals arrive in M8. Exit with code 0.
    - _Requirements: 3.3, 7.1, 1.3_

  - [ ]* 8.3 Write integration tests for truth bootstrapping
    - `tests/integration/test_truth_bootstrap.py`: `ensure_truth_collections` creates `ground_truth` with its validator and named indexes in the truth test database, and is idempotent.
    - A source scan asserts that `ensure_truth_collections` is referenced only from `bootstrap.py`, `datagen/` and tests, and never from `backend/app/main.py`, `core/` or `api/`.
    - **Property 7: Truth isolation by construction (call-site part)**
    - **Validates: Requirements 6.7, 2.3, 3.3**

- [ ] 9. Checkpoint: run lint, type checks and tests
  - Run `docker compose up -d`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` and `uv run pytest`. Report the real results, including failures. Ensure all tests pass, and ask the user if questions arise.
  - _Requirements: 8.4_

- [ ] 10. Add the quality gates
  - [ ] 10.1 Create `mulescope/.pre-commit-config.yaml`
    - Add the `ruff` hook (lint with `--fix`) and the `ruff-format` hook. Add a local `mypy` hook that runs `uv run mypy` with `language: system` and `pass_filenames: false`, so it uses the strict config from `pyproject.toml`.
    - Document `uv run pre-commit install` in the README Setup section.
    - _Requirements: 8.1, 8.2, 1.6_

  - [ ] 10.2 Create `.github/workflows/ci.yml`
    - It runs on push and pull request, on `ubuntu-latest`, with a `mongo:7` service container on port 27017 and a health check.
    - Steps:
      - `actions/checkout`
      - `astral-sh/setup-uv` with Python 3.12
      - `uv sync --frozen`
      - `uv run ruff check .`
      - `uv run ruff format --check .`
      - `uv run mypy`
      - `uv run pytest`, with `MONGO_URI` pointing at the service and `LLM_MODE=fallback`
    - Use `working-directory: mulescope`.
    - _Requirements: 8.3, 8.1, 8.2_

  - [ ] 10.3 Run every quality gate and fix all findings
    - Run `uv run lint` and `uv run pytest` in PowerShell. Fix any ruff, mypy `--strict` (`domain/`, `services/`, `graph/`) or test failures in the affected files. Record the real results.
    - _Requirements: 8.1, 8.2, 8.4_

- [ ] 11. Verify the M0 acceptance check and record progress
  - [ ] 11.1 Write `tests/integration/test_m0_acceptance.py`
    - Using `TestClient(create_app(test_settings))`, which runs the full lifespan, assert that:
      - `GET /health` returns 200 `{"status": "ok", "db": "ok"}`
      - every operational collection from the plan exists
      - every named index exists
      - both checkpointer TTL indexes exist
    - Add a manual verification snippet to the README Setup section for the user to run in their own terminal: `docker compose up -d`, `uv run dev`, then `Invoke-RestMethod http://localhost:8000/health` in a second PowerShell window.
    - _Requirements: 5.1, 5.2, 5.4, 6.1, 6.2, 6.5_

  - [ ] 11.2 Update `PROGRESS.md` at the workspace root
    - **Status:** M0 done, with the real lint, type and test results.
    - **Done:** the list of delivered pieces.
    - **Next:** M1, synthetic data and the detector.
    - **Decisions:**
      - native async PyMongo instead of Motor
      - split settings, so the API has no truth URI
      - `/health` at the root path
      - `DependencyUnavailable` maps to 503
      - per-collection `_id` validators
      - full M1 validators now
      - checkpointer retention via the native `MongoDBSaver(ttl=...)` on a dedicated sync client built off-loop. The corrected decision: an earlier draft assumed string timestamps and deferred the TTL to M4, and reading the saver source showed it stamps BSON `created_at` and creates its own TTL indexes.
      - `llm_cache` TTL sourced from `config/llm.yaml`
      - `pyyaml` and dev-only `httpx` added, with their reasons
      - property tests written as exhaustive parametrized pytest checks because Hypothesis is not in the stack
      - seed and evals stubs log instead of printing
    - **Known gaps:**
      - repositories, services and graph are placeholders
      - baseline-only validators for the collections populated from M3 onward
      - TTL monitor latency of about 60 seconds
      - frontend tooling deferred to M6
    - _Requirements: 8.4_

- [ ] 12. Final checkpoint: ensure all tests pass
  - Run `uv run lint` and `uv run pytest` against `docker compose up -d` Mongo, and report the real results, including failures. Ensure all tests pass, and ask the user if questions arise.
  - _Requirements: 8.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. Core implementation tasks are never optional.
- Hypothesis is not in the section 2 stack and is not added. The design's correctness properties apply to finite, enumerable sets: every domain module, every collection, every index spec and every `DomainError` subclass. They are implemented as exhaustive `pytest.mark.parametrize` checks over those sets.
- Two dependencies sit outside the plain framework list, each with its stated reason: `pyyaml`, for the YAML config that section 10.2 mandates, and `httpx`, dev-only, required by FastAPI's `TestClient` and not a transitive dependency of `fastapi`. `uvicorn` is flagged as the ASGI server that `uv run dev` requires.
- `ensure_collections` takes `llm_cache_ttl_seconds` as a parameter, an addition to the design signature, so the 30-day TTL comes from `config/llm.yaml` rather than a literal (Requirement 3.6).
- Integration tests need local MongoDB. Run `docker compose up -d` from `mulescope/` first.
- `uv run dev` is a long-running server. Run it manually in your own terminal, and rely on the automated acceptance test (11.1) for verification.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["2.2", "2.3", "2.4", "2.5", "3.1"] },
    { "id": 2, "tasks": ["2.1", "4.1", "4.2", "3.2"] },
    { "id": 3, "tasks": ["4.3", "2.6", "6.1", "6.2"] },
    { "id": 4, "tasks": ["4.4", "6.3", "7.1", "8.1", "8.2"] },
    { "id": 5, "tasks": ["4.5", "4.6", "4.7", "6.4", "7.2", "7.3", "8.3"] },
    { "id": 6, "tasks": ["7.4"] },
    { "id": 7, "tasks": ["7.5"] },
    { "id": 8, "tasks": ["7.6", "7.7", "7.8", "2.7", "2.8", "10.1", "10.2"] },
    { "id": 9, "tasks": ["10.3"] },
    { "id": 10, "tasks": ["11.1"] },
    { "id": 11, "tasks": ["11.2"] }
  ]
}
```

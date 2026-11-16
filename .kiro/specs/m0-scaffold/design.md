# Design Document

## Overview

M0 delivers the MuleScope scaffold: a runnable FastAPI backend wired to a real local MongoDB 7, a layered architecture with a single composition root, startup collection bootstrapping (validators plus indexes), structured logging, a central error handler, and the quality gates (ruff, mypy, pytest, pre-commit, GitHub Actions). It also lays down the empty-but-structured directory tree, config placeholders, a `.gitignore`, and a `README.md` stub that M1 onward fill in.

The guiding constraints come directly from the build prompt: the stack in section 2 is fixed and closed (no added dependencies), the architecture in section 3 is strictly layered with dependencies pointing inward, the folder tree in section 4 is created exactly, the MongoDB conventions in section 5 are enforced at the collection boundary, and the code standards in section 10.2 (full type hints, async I/O, no magic numbers, JSON logging, secrets from env) apply from the first commit.

**Acceptance target (section 11):** `uv run dev` starts, `GET /health` is green, and all collections and indexes exist.

### Goals

- A FastAPI app that starts via `uv run dev`, serves `GET /health` at the root path, and serves `GET /api/v1/config/public`.
- MongoDB 7 running locally through Docker Compose, with a native async PyMongo client and a pool created once.
- `ensure_collections()` that creates every operational collection with its JSON Schema validator and named indexes, idempotently; full validators for the M1 collections; and a separate `ensure_truth_collections()` for the truth database called only by datagen.
- A composition root that builds dependencies and injects them with FastAPI `Depends`, with layering that keeps `domain` free of framework imports.
- Structured JSON logging, a `DomainError` hierarchy (including `DependencyUnavailable`), and one exception-to-HTTP handler.
- Working lint, type-check, test, and CI configuration, plus `.gitignore` and a README stub.

### Non-goals

- No synthetic data, detector, scoring, graph nodes, LLM providers, repository method bodies, or frontend application. The frontend and its tooling (strict TypeScript, ESLint, Prettier) arrive in M6; M0 only creates the `frontend/src/` directory placeholders.

## Architecture

### Layering (section 3)

Dependencies point inward only. The arrows below show allowed import direction.

```text
api/routers  ->  services  ->  repositories (interfaces) <- repositories/mongo
     |               |                 |
     v               v                 v
 api/schemas       domain  <----------- (all layers may import domain)
                     ^
core/container ------+   (composition root: may import everything, imported by main.py via Depends)
```

Rules enforced in M0:

- Nothing in `domain/` imports FastAPI, PyMongo, or LangGraph. Verified by a unit test that imports every `domain` module with those packages assert-absent from its module graph (import-guard test).
- Controllers are thin: validate input, call one service, return a schema. In M0 the only controllers are the health and config routes.
- Services and nodes receive collaborators through constructors or `RunnableConfig`; no global client singletons, no `import db` inside a node.

### Process and settings boundaries

Three entry-point processes exist, each with its own settings object so the API can never reach the truth database:

- **API process** (`uv run dev`): loads `ApiSettings`, which carries only the operational `mulescope` connection. No `mongo_truth_uri` field exists on it.
- **Datagen process** (`uv run seed`): loads `DatagenSettings`, which extends the shared base with the truth connection string, and is the only caller of `ensure_truth_collections()`.
- **Evals process** (`uv run evals`): loads `EvalsSettings`, which also carries the truth connection string (read-only use).

### Component diagram (M0 API runtime)

```text
             uv run dev
                 |
                 v
        +------------------+
        |  main.py         |  app factory + lifespan
        |  create_app()    |
        +--------+---------+
                 | builds at startup
                 v
        +------------------+        +----------------------+
        |  core/container  |------->|  Mongo async client  | (pool once)
        |  Container       |        |  mulescope DB only   |
        +--------+---------+        +----------+-----------+
                 |                              |
                 |                              v
                 |                   ensure_collections()
                 |                   (validators + indexes)
                 |
                 |                  +----------------------+
                 +----------------->|  Mongo sync client   | (pool once)
                 |                  |  checkpointer only   |
                 |                  +----------+-----------+
                 |                              |
                 |                              v
                 |                   MongoDBSaver(ttl=7d)
                 |                   (own compound + created_at TTL
                 |                    indexes on checkpoints /
                 |                    checkpoint_writes)
                 v
        +------------------+
        |  routes          |  /health (root) + /api/v1/config/public
        +------------------+
                 ^
                 | Depends()
        +------------------+
        |  api/deps.py     |  resolves container-built objects
        +------------------+
```

### Startup sequence (lifespan)

1. Load `ApiSettings` (pydantic-settings) from environment and `.env`.
2. Build the `Container`: create the async Mongo client (pool once), resolve the `mulescope` database handle, and construct placeholder providers/services.
3. Run `ensure_collections(db)` to create collections, validators, and indexes idempotently.
4. Off the event loop (`asyncio.to_thread`), create the sync `MongoClient` (pool once, checkpointer only) and construct `MongoDBSaver(client=sync_client, db_name=settings.mongo_db_name, ttl=settings.checkpoint_ttl_seconds)`, whose `__init__` creates its own indexes.
5. Compile the LangGraph graph once with that checkpointer (M0 uses a trivial placeholder builder so the wiring exists; real nodes arrive in M4).
6. Yield (app serves requests).
7. On shutdown: close both the async operational client and the sync checkpointer client.

## Components and Interfaces

### core/settings.py

A shared `BaseAppSettings(BaseSettings)` holds common fields. `ApiSettings` is what the API process loads and deliberately has **no** `mongo_truth_uri`. `DatagenSettings` and `EvalsSettings` add the truth connection. All fields are fully typed; no literal thresholds live in code.

`BaseAppSettings` (common):

| Field | Type | Source | Notes |
| --- | --- | --- | --- |
| `mongo_uri` | `str` | env `MONGO_URI` | operational `mulescope` connection |
| `mongo_db_name` | `str` | env, default `mulescope` | |
| `groq_api_key` | `str \| None` | env `GROQ_API_KEY` | not required in fallback |
| `gemini_api_key` | `str \| None` | env `GEMINI_API_KEY` | not required in fallback |
| `llm_mode` | `LlmMode` enum | env `LLM_MODE`, default `fallback` | `live` or `fallback` |
| `as_of_date` | `date` | env `AS_OF_DATE`, default `2026-10-31` | dataset end date |
| `graph_version` | `str` | const/config | stamped on runs |
| `checkpoint_ttl_days` | `int` | env `CHECKPOINT_TTL_DAYS`, default `7` | checkpointer retention; used by the API |
| `checkpoint_ttl_seconds` | `int` (derived property) | computed from `checkpoint_ttl_days` | passed to `MongoDBSaver(ttl=...)` |

`ApiSettings(BaseAppSettings)`: adds nothing database-related; explicitly omits any truth URI.

`DatagenSettings(BaseAppSettings)` / `EvalsSettings(BaseAppSettings)`:

| Field | Type | Source | Notes |
| --- | --- | --- | --- |
| `mongo_truth_uri` | `str` | env `MONGO_TRUTH_URI` | truth DB connection; loaded only by datagen/evals |
| `mongo_truth_db_name` | `str` | env, default `mulescope_truth` | |

`.env.example` lists every variable, including `MONGO_TRUTH_URI`, with a comment that it is used only by datagen and evals, and `CHECKPOINT_TTL_DAYS` (default 7) for checkpointer retention. Keys are never committed.

### core/container.py

```python
class Container:
    """Composition root. Builds clients, repositories, providers and the
    compiled graph, and exposes them for FastAPI Depends. Imported by main.py
    and api/deps.py only. Built from ApiSettings; never holds a truth handle."""

    def __init__(self, settings: ApiSettings) -> None: ...
    @property
    def db(self) -> AsyncDatabase: ...        # mulescope operational handle only
    @property
    def checkpointer(self) -> MongoDBSaver: ...   # built on the sync client, checkpointer only
    def repositories(self) -> RepositoryBundle: ...   # placeholders in M0
    def services(self) -> ServiceBundle: ...          # placeholders in M0
    async def startup(self) -> None: ...      # connect + ensure_collections + build checkpointer off-loop + compile graph
    async def shutdown(self) -> None: ...     # close async client and sync checkpointer client
```

In M0 the repository and service bundles hold the concrete-but-minimal objects needed for health and config routes; richer members arrive in later milestones without changing the container's shape.

### core/logging.py

A single `get_logger(name)` factory returning a logger that emits structured JSON. A context mechanism (contextvars) carries `case_id` and `run_id` so every line within a run includes them. No `print` anywhere.

### core/errors.py

```python
class DomainError(Exception): ...
class NotFound(DomainError): ...
class PolicyViolation(DomainError): ...
class LLMUnavailable(DomainError): ...
class DependencyUnavailable(DomainError): ...   # infrastructure failure (e.g. DB unreachable)
```

One FastAPI exception handler maps these to HTTP status codes and a consistent error envelope:

| Exception | HTTP | Envelope `code` |
| --- | --- | --- |
| `NotFound` | 404 | `not_found` |
| `PolicyViolation` | 409 | `policy_violation` |
| `LLMUnavailable` | 503 | `llm_unavailable` |
| `DependencyUnavailable` | 503 | `dependency_unavailable` |
| `DomainError` (base) | 400 | `domain_error` |
| unhandled | 500 | `internal_error` |

Error envelope shape: `{ "error": { "code": str, "message": str, "detail": object | null } }`.

### repositories/mongo/bootstrap.py

`async def ensure_collections(db) -> None` creates every operational collection with a JSON Schema validator and named indexes, and is idempotent (uses `collMod` to apply/refresh validators on existing collections and `create_index` which is a no-op when the index already exists). `async def ensure_truth_collections(truth_db) -> None` lives alongside it but is imported and called only by `datagen`; it is never referenced from the API startup path.

Collection and index plan (from section 5):

| Collection | Key indexes (named) | `_id` type |
| --- | --- | --- |
| `customers` | `risk_rating` | string `CUS-` |
| `accounts` | `customer_id`; unique `account_no`; unique `vpa` | string `ACC-` |
| `counterparties` | unique `vpa` | string `CPY-` |
| `transactions` | `(account_id, ts)`; `(counterparty.ref_id, ts)`; `transfer_id` | ObjectId |
| `complaints` | `beneficiary_ref`; `linked_transfer_ids` | string `CMP-` |
| `users` | unique `email` | string `USR-` |
| `alerts` | unique `dedupe_key`; `(status, priority)`; `account_id` | string `ALT-` |
| `cases` | `(status, priority, sla_due_at)`; unique `alert_id`; `assigned_to` | string `CASE-` |
| `case_runs` | `(case_id, started_at desc)` | string `RUN-` |
| `node_executions` | `(run_id, started_at)` | ObjectId |
| `evidence` | `(case_id, run_id)` | string `EVD-` |
| `reports` | `(case_id, version desc)` | string `RPT-` |
| `actions` | `(case_id, status)`; `(status, due_at)` | string `ACT-` |
| `decisions` | `(case_id, created_at)` | string `DEC-` |
| `audit_logs` | `(case_id, ts)`; `(entity.type, entity.id)`; `ts` | ObjectId |
| `llm_cache` | unique `key`; TTL 30 days on `created_at` | string (hash) |
| `eval_runs` / `eval_results` | `run_id` | string |
| `dataset_meta` | none | string |
| `checkpoints`, `checkpoint_writes` | owned by `MongoDBSaver`; unique compound index + `created_at` TTL (7 days) created by the saver; never written by our bootstrap | library-defined |

Truth database (`ensure_truth_collections`): `ground_truth` with indexes on `account_id` and `scenario_type`, `_id` string.

Conventions enforced by the validators: `snake_case` fields, the correct `_id` type per collection as listed above (prefixed-string `pattern` for business entities, `bsonType: objectId` for high-volume append-only data), Decimal128 INR money (`bsonType: decimal`), UTC `datetime` (`bsonType: date`), `created_at` required on all documents and `updated_at` + `schema_version` on mutable ones.

**Full validators for the M1 collections.** `ensure_collections()` defines complete JSON Schema validators (required fields and field `bsonType`s, not only a baseline) for the collections M1 writes: `customers`, `accounts`, `counterparties`, `transactions`, `complaints`, `alerts`, and `dataset_meta`. These assert, for example, that `accounts` has a string `_id` matching `^ACC-`, a required `customer_id`, `account_no`, `type`, `status`, a decimal `balance`, and date `created_at`; and that `transactions` has an `objectId` `_id`, required `transfer_id`, `account_id`, `direction`, decimal `amount`, and date `ts`. The remaining operational collections (populated from M3+) get a baseline validator (`_id` type, required `created_at`) in M0 and are tightened as those entities are implemented.

Indexes are ensured at startup; where later milestones bulk-load data, index creation happens after the load (section 5), but in M0 there is no data so startup ensuring is sufficient.

**Checkpointer collections and the 7-day retention (verified).** The `langgraph-checkpoint-mongodb` package (`langgraph.checkpoint.mongodb`) exports `MongoDBSaver(client: MongoClient, db_name, checkpoint_collection_name="checkpoints", writes_collection_name="checkpoint_writes", ttl: Optional[int] = None, serde=None)`, confirmed against `saver.py` on main. Its async methods (`aget_tuple`, `aput`, ...) wrap the sync calls in `run_in_executor`, so they do not block the event loop; there is no separate async saver.

1. **We pass our own sync client.** The container creates one synchronous PyMongo `MongoClient` at startup (pool once), used only by the checkpointer, and constructs `MongoDBSaver(client=sync_client, db_name=settings.mongo_db_name, ttl=settings.checkpoint_ttl_seconds)`. This is the only sync client in the API process; the async operational client is unaffected. The sync client is closed on shutdown.
2. **The saver manages retention natively.** With `ttl` set, the saver stamps a BSON `created_at` (UTC) on every document in both `checkpoints` and `checkpoint_writes`, and creates a TTL index on `created_at` with `expireAfterSeconds=ttl` on both collections, plus unique compound indexes on `(thread_id, checkpoint_ns, checkpoint_id[, task_id, idx])`. Our `ensure_collections()` never creates indexes on or writes to these collections.
3. **Construction is off-loop.** Index creation runs in the saver's `__init__` and is blocking, so the lifespan constructs it via `asyncio.to_thread` so no blocking call runs on the event loop.
4. **Caveats.** TTL deletion is performed by MongoDB's TTL monitor (runs about every 60 seconds), so expiry is not instantaneous. The library version is pinned in `uv.lock`, and an integration test asserting the saver-created TTL indexes guards against API drift on upgrade.

### api/main.py and routers

- `create_app() -> FastAPI` builds the app, registers the error handler, mounts the root `/health` route and the `/api/v1` routers, and wires the lifespan to `Container.startup`/`shutdown`.
- Routes in M0:
  - `GET /health` (root path, not under `/api/v1`) -> `{ "status": "ok", "db": "ok" }` after a lightweight Mongo ping; a failed ping raises `DependencyUnavailable` and returns 503 via the error handler.
  - `GET /api/v1/config/public` -> `{ "llm_mode", "graph_version", "providers": {...} }`.
- Placeholder router modules for `alerts`, `cases`, `accounts`, `actions`, `audit`, `evals`, `stream` exist with docstrings and no endpoints yet, so M3+ adds handlers without restructuring.

### api/deps.py

Thin `Depends` providers that pull the already-built objects off the `Container` stored on `app.state`. No object construction per request.

## Data Models

M0 defines only the enums and the minimal response schemas needed for the health and config routes; full entities arrive in M2/M3.

- `domain/enums.py`: `LlmMode(live, fallback)`, and placeholders imported later (`Disposition`, `Channel`, `ActionType`, statuses) stubbed as needed for typing. Every closed set is an enum (section 10.2).
- `api/schemas/system.py`: `HealthResponse`, `PublicConfigResponse` (Pydantic v2), kept separate from domain entities.

Money and time conventions (Decimal128 INR, UTC datetime) are enforced in `bootstrap.py` validators and supported by a `core/clock.py` that provides the single time source (so nothing calls `datetime.now()` directly).

## Project layout created in M0

The full section-4 tree is created. Directories that hold no M0 logic still get `__init__.py` with a module docstring. Additional root files created in M0:

- `.gitignore` — Python caches (`__pycache__`, `*.pyc`), virtualenvs and `uv` artefacts (`.venv`), `.env` and local env files, build and dist output, test and coverage output (`.pytest_cache`, `.mypy_cache`, `.coverage`, `htmlcov`), editor/OS files (`.idea`, `.vscode` local, `.DS_Store`), and frontend `node_modules` and build output.
- `README.md` stub — project name, one-line description, the in-scope and out-of-scope lists from section 1, and placeholder sections for setup, architecture diagram, and eval results to be filled in later milestones.
- `config/` placeholders (`llm.yaml`, `scoring.yaml`, `playbook.yaml`, `scenarios.yaml`) with commented skeletons and `TODO verify` notes where regulatory values will later live.
- `docker-compose.yml` running MongoDB 7 only.

`pyproject.toml` declares scripts:

| Script | Command target | M0 behaviour |
| --- | --- | --- |
| `uv run dev` | uvicorn app factory | starts the API |
| `uv run seed` | `datagen.cli:main` | stub that prints "not implemented until M1" |
| `uv run evals` | `evals` entry | stub that prints "not implemented until M8" |
| lint script | `ruff check` + `mypy` | runs lint and types |

All scripts are invoked through `uv run ...` and work in PowerShell; no Makefile is introduced.

## Error Handling

- A single registered handler translates the `DomainError` hierarchy and unhandled exceptions into the error envelope above.
- The health route depends on a Mongo ping; a failed ping raises `DependencyUnavailable` (mapped to 503), never an unhandled 500.
- Logging: every handled error logs one structured JSON line including `case_id`/`run_id` when present.

## Testing Strategy

Tests run against a real local MongoDB (section 10.4), not mongomock. `tests/conftest.py` spins up a test database (separate name) and drops it after the module.

| Level | M0 tests |
| --- | --- |
| Unit | Import-guard test (no FastAPI/PyMongo/LangGraph imported by `domain/`); error-to-HTTP mapping incl. `DependencyUnavailable` -> 503; `ApiSettings` has no `mongo_truth_uri` attribute while `DatagenSettings` does; logger emits valid JSON with `case_id`/`run_id`. |
| Integration | `ensure_collections()` creates every expected collection and named index (assert index names, uniqueness, TTL options), applies the correct `_id` validator per collection, and is idempotent on a second run; full M1-collection validators reject a document with a wrong-typed field and accept a valid one. `GET /health` at the root path returns ok against a live Mongo and 503 when the DB is down. `GET /api/v1/config/public` returns the configured mode and versions. `ensure_truth_collections()` creates `ground_truth` in the truth DB and is not invoked by app startup. After app startup, both `checkpoints` and `checkpoint_writes` have a `created_at` TTL index with `expireAfterSeconds` equal to the configured `checkpoint_ttl_seconds`; running `ensure_collections()` alone (without the checkpointer) does not create those indexes. |
| Tooling | `ruff check` clean; `mypy --strict` clean on `domain/`, `services/`, `graph/`; pre-commit config runs these hooks; GitHub Actions workflow runs lint, types, and tests with a MongoDB service container. |

Coverage targets (80% on `domain/` and `services/`) apply as those layers gain logic; in M0 the small amount of domain/service code is covered by the tests above.

## Decisions and rationale

- **Native async PyMongo, not Motor** — mandated by section 2 (Motor is deprecated). The container holds one client; the pool is created once.
- **Split settings; API has no truth URI** — a structural guarantee (stronger than a convention) that the API and agents cannot reach `mulescope_truth` (section 5). The truth connection exists only on `DatagenSettings`/`EvalsSettings`, and `ensure_truth_collections()` is called only by datagen.
- **Health at the root path** — `GET /health` is an operational probe (used by Docker/Render/Vercel health checks), so it sits at `/health`, outside the versioned `/api/v1` surface; everything else stays versioned.
- **`DependencyUnavailable` (503)** — infrastructure failures such as an unreachable database are distinct from LLM outages; giving them their own `DomainError` subclass keeps the health route honest and avoids overloading `LLMUnavailable`.
- **Per-collection `_id` types in validators** — section 5 specifies readable prefixed-string ids for business entities and ObjectId for high-volume append-only data; encoding this in each validator catches id-shape mistakes at write time.
- **Full validators for M1 collections now** — M1 is the next milestone and writes customers, accounts, counterparties, transactions, complaints, alerts, and dataset_meta; defining their complete validators in M0 means the seeded data is schema-checked from the first insert.
- **Checkpointer retention via the native `ttl` parameter, on a dedicated sync client, built off-loop** — `MongoDBSaver` accepts only a sync `MongoClient`, so the container creates one (pool once) solely for it. Passing `ttl=settings.checkpoint_ttl_seconds` (7 days from config) makes the saver stamp a BSON `created_at` and create its own TTL indexes on both checkpoint collections, so our bootstrap leaves them alone. Its blocking `__init__` runs via `asyncio.to_thread` to keep the event loop free. An earlier draft claimed the saver stored a string timestamp and deferred TTL to M4; that was corrected after reading the saver source.
- **Placeholder graph compile in the lifespan** — section 7 says compile the graph once at startup; M0 compiles a trivial graph so the wiring and `thread_id` plumbing exist before real nodes land in M4.
- **Config YAML placeholders now** — section 10.2 forbids magic numbers; creating the YAML files in M0 gives later milestones a home for weights, thresholds, and model names from day one.
- **Frontend tooling deferred to M6** — M0 creates the `frontend/src/` directories but no TypeScript/ESLint/Prettier config; that tooling ships with the frontend in M6.
- **PowerShell-only commands, no Makefile** — section 2 states the dev machine is Windows; all scripts run through `uv run`.

## Correctness Properties

These are invariants that must hold for M0 and are directly testable.

### Property 1: Layer isolation

For every module under `domain/`, its transitive import set contains none of `fastapi`, `pymongo`, or `langgraph`. Verified by an import-guard unit test.

**Validates: Requirements 4.2**

### Property 2: Bootstrap idempotency

Running `ensure_collections(db)` twice yields the same set of collections and named indexes as running it once, with no error and no duplicate indexes.

**Validates: Requirements 6.1, 6.8**

### Property 3: Index and validator completeness

After `ensure_collections(db)`, every named operational index listed in the bootstrap plan exists on its collection, with the correct `unique` and TTL options (`llm_cache` unique `key` plus a 30-day TTL on `created_at`), and each collection's validator enforces the `_id` type listed in the plan. Additionally, after app startup, the checkpointer-created `created_at` TTL index with `expireAfterSeconds` equal to the configured 7 days exists on both `checkpoints` and `checkpoint_writes` (asserted by test, but created by `MongoDBSaver`, not by our bootstrap).

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

### Property 4: Client ownership

The API process creates exactly one async operational Mongo client and exactly one sync Mongo client, and the sync client is used only by the checkpointer. Request handlers obtain database handles from the container, never by constructing a client. Our bootstrap never writes to or creates indexes on `checkpoints` or `checkpoint_writes`.

**Validates: Requirements 2.4, 2.5, 4.3, 6.5**

### Property 5: Error envelope totality

Every raised `DomainError` subclass, including `DependencyUnavailable`, maps to a defined HTTP status and the standard envelope; no `DomainError` reaches the client as a 500.

**Validates: Requirements 7.3, 7.4**

### Property 6: Health truthfulness and placement

`GET /health` is served at the root path and returns `db: ok` only when a live Mongo ping succeeds; a failed ping returns 503, never 200.

**Validates: Requirements 5.2, 5.4**

### Property 7: Truth isolation by construction

`ApiSettings` exposes no truth connection field, and the API `Container` holds no truth database handle; the truth connection exists only on datagen/evals settings, and `ensure_truth_collections()` is never called during API startup.

**Validates: Requirements 2.3, 3.2, 3.3, 6.7**

### Property 8: No secrets in code

No API key literal appears in source; all keys resolve from environment variables, and `.env.example` enumerates every variable.

**Validates: Requirements 3.4, 3.5**

### Property 9: Config sourcing

No threshold, weight, model name, timeout, or limit is a literal in `domain/`, `services/`, or `graph/`; such values come from settings or `config/*.yaml`.

**Validates: Requirements 3.6**

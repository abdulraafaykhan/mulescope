---
inclusion: always
---

# Structure

## 3. Architecture, MVC and SOLID

The backend is layered. Dependencies point **inward only**: controllers call services, services call repositories and agents, nothing in `domain` imports FastAPI, PyMongo or LangGraph.

| Layer | MVC role | Lives in | Responsibility | May import |
| --- | --- | --- | --- | --- |
| Domain | Model | `domain/` | Pydantic entities, enums, value objects, pure scoring and metric functions | stdlib, pydantic |
| Repositories | Model | `repositories/` | All MongoDB access, one class per collection, behind abstract interfaces | domain |
| Services | Model (use cases) | `services/` | Business flows: detect alerts, run a case, apply analyst decision, build report | domain, repository interfaces |
| Agents and graph | Model (AI) | `agents/`, `graph/` | LangGraph state, nodes, edges, prompts, tools | domain, services, repository interfaces |
| Controllers | Controller | `api/routers/` | Thin HTTP handlers: validate, call one service, return a schema. No logic. | services, schemas |
| Schemas | View contract | `api/schemas/` | Request and response DTOs, separate from domain entities | domain |
| UI | View | `frontend/` | React app. Talks only to `/api/v1` and the SSE stream. | API only |
| Composition root |  | `core/container.py` | Builds repositories, services, LLM providers and the compiled graph, and injects them with FastAPI `Depends` | everything |

**SOLID, as concrete rules the code must follow**

- **Single responsibility.** One reason to change per class. A node does one thing. A repository only touches its own collection. A router has no business logic.
- **Open/closed.** New signals, actions and typologies are added by registering a class or a YAML entry, never by editing an `if/elif` chain. Use a **signal registry** (`@register_signal`) and an **action playbook** loaded from `config/playbook.yaml`.
- **Liskov.** Every `LLMProvider` (Groq, Gemini, Template fallback) and every repository implementation is substitutable behind its interface, and the tests prove it with the same contract suite.
- **Interface segregation.** Small interfaces: `AlertRepository`, `CaseRepository`, `TransactionQueryPort`, `AuditSink`, `LLMProvider`. A service depends only on the ports it uses.
- **Dependency inversion.** Services and graph nodes receive their dependencies through constructors or `RunnableConfig`. No global clients, no `import db` inside a node.

**Other design rules**

- **Agent tools are read-only ports** over a narrow query API (`get_account_profile`, `get_flow_metrics`, `get_counterparties`). Agents never receive a raw database handle and can never read the `ground_truth` collection.
- **Typed everywhere.** Pydantic models for all state, tool inputs and outputs, and structured LLM output (`with_structured_output`). Free-form text is only allowed in narrative fields.
- **Errors.** A small exception hierarchy (`DomainError`, `NotFound`, `PolicyViolation`, `LLMUnavailable`) mapped to HTTP codes in one handler.
- **Idempotency.** Running a case twice for the same alert and graph version reuses or replaces the previous run, never duplicates it.

## 4. Folder and file structure

Create exactly this layout. Every module gets a module docstring explaining its role and who calls it.

```text
./                            # repository root (no mulescope/ subfolder)
├── pyproject.toml            # uv project, scripts: seed, dev, evals, lint
├── docker-compose.yml        # local MongoDB 7 only
├── .env.example
├── README.md                 # architecture diagram, setup, eval results, scope
├── config/
│   ├── llm.yaml              # models, temperatures, limits per agent
│   ├── scoring.yaml          # signal weights and thresholds
│   ├── playbook.yaml         # verdict/signal -> action mapping
│   └── scenarios.yaml        # planted scenario counts and parameters
├── backend/
│   └── app/
│       ├── main.py           # FastAPI app factory, lifespan, graph compile
│       ├── core/             # settings, container (DI), logging, errors, clock
│       ├── domain/           # entities, enums, value objects, pure functions
│       │   ├── entities/     # account, customer, transaction, alert, case, action
│       │   ├── signals/      # one file per signal + registry
│       │   └── policy/       # scoring.py, disposition.py
│       ├── repositories/     # interfaces/ + mongo/ implementations
│       ├── services/         # detection, case_runner, decision, report, evals
│       ├── agents/           # profiler, flow_analyst, narrative, critic
│       │   ├── prompts/      # versioned prompt files, one per agent
│       │   └── tools/        # read-only tools exposed to agents
│       ├── graph/            # state.py, nodes/, edges.py, builder.py, checkpoint.py
│       ├── llm/              # provider interface, groq, gemini, template, cache, limiter
│       └── api/
│           ├── routers/      # alerts, cases, accounts, actions, audit, evals, stream
│           ├── schemas/      # request/response DTOs
│           └── deps.py
├── datagen/                  # synthetic data package (own CLI: uv run seed)
│   ├── cli.py
│   ├── factories/            # customers, accounts, background transactions
│   ├── scenarios/            # one class per planted scenario type
│   ├── writers.py            # bulk insert, index creation
│   └── validate.py           # post-seed sanity checks
├── evals/                    # harness, golden cases, metrics, report
├── tests/
│   ├── unit/                 # signals, scoring, policy, repositories contracts
│   ├── integration/          # API and graph runs in fallback LLM mode
│   └── conftest.py
└── frontend/
    └── src/
        ├── app/              # router, providers, layout
        ├── features/         # queue, case-workspace, flow-graph, agents, actions, audit, evals
        ├── components/ui/    # shadcn primitives
        ├── lib/              # api client, sse hook, formatters (INR, IST, masking)
        ├── styles/           # tokens.css, tailwind config
        └── types/            # generated from the OpenAPI schema
```

**File rules**

- One class or one cohesive set of functions per file, under about 250 lines. Split when larger.
- Names describe behaviour: `rapid_exit_signal.py`, not `utils2.py`. No `utils.py` or `helpers.py` dumping grounds.
- Every public function and class has a docstring stating purpose, inputs, outputs and failure modes. Comments explain **why**, not what.
- Frontend types come from the backend OpenAPI schema (`openapi-typescript`), never hand-copied.

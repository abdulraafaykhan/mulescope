# PROGRESS

Checklist of build phases. If context is lost, continue from the first unchecked item.
Source of truth for stack, data model, graph, scoring and UI: `docs/BUILD_PROMPT.md`.
Process, testing and scope follow the latest user instructions (no specs, no test suites,
smoke commands only, commit after each phase, stop after phase 3).

## Phases

- [x] Phase 0: finish M0 (container, API layer, main.py, entry points)
- [ ] Phase 1: synthetic data and detector
- [ ] Phase 2: domain logic (metrics, signals, policy, planner, `uv run check-policy`)
- [ ] Phase 3: API and graph in fallback mode (`uv run smoke`)
- [ ] Phase 4: live LLM agents (not started, out of scope for this run)
- [ ] Phase 5: analyst UI (not started)
- [ ] Phase 6: evals and README (not started)

## Decisions

- MongoDB is Atlas (from the workspace `.env`, read-only). No local Docker on this machine.
- Settings read both `mulescope/.env` and the workspace `.env`; empty `*_API_KEY=` counts as unset.
- `/health` at the root path; all other routes under `/api/v1`.
- Checkpointer: `MongoDBSaver(ttl=7 days)` on a dedicated sync client built off the event loop.
- `uv run lint`, pre-commit and CI removed from scope. Existing test files are kept but not run.

## Known gaps

- (none yet)

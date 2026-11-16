# MuleScope

A LangGraph-based AML triage copilot for mule-account / rapid pass-through alerts.

## Scope

A bank's detector flags an account that receives money from many senders and moves it out within minutes. MuleScope investigates that alert, scores it, recommends **Close**, **Escalate** or **STR Draft**, drafts the narrative, and waits for an analyst to approve. Execution of actions (holds, KYC refresh) is mocked by writing to the database.

### In scope

- Alert detection
- Case queue
- Two investigation agents (Profiler and Flow Analyst) plus a narrative writer and a critic
- Deterministic scoring and policy
- Action planner and mock executor
- Analyst approval (maker-checker for STR)
- Audit trail
- Diagnostics
- Case report export
- Evals

### Out of scope

- Card fraud
- Account takeover
- Phishing
- Sanctions screening
- Real-time blocking
- Real bank integrations
- Real customer data

## Setup

All commands run in PowerShell from the `mulescope/` directory.

```powershell
# Install dependencies (Python 3.12, uv)
uv sync

# Copy the environment template and fill in values
Copy-Item .env.example .env

# Start local MongoDB
docker compose up -d

# Start the API
uv run dev
```

_TODO: complete in later milestones (seeding, evals, frontend)._

## Architecture

_TODO: to be documented in later milestones._

## Eval results

_TODO: no eval results yet. Populated once evals run (M8)._

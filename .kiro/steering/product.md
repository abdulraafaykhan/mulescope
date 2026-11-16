---
inclusion: always
---

# Product: MuleScope

Build **MuleScope**, a LangGraph-based AML triage copilot for one alert type: **mule-account / rapid pass-through activity**.

## 1. Mission and scope

A bank's detector flags an account that receives money from many senders and moves it out within minutes. MuleScope investigates that alert, scores it, recommends **Close**, **Escalate** or **STR Draft**, drafts the narrative, and waits for an analyst to approve. Execution of actions (holds, KYC refresh) is mocked by writing to the database.

**Non-negotiables**

- The LLM investigates, explains and writes. **Metrics, scores and the disposition are deterministic code.** An agent can argue for a different outcome, but only a human can override the policy, and the reason is logged.
- **Synthetic data is a first-class deliverable.** It must be realistic, seeded and reproducible, and carry planted scenarios with hidden ground truth.
- Everything runs on **free tiers**. Never assume paid quotas. LLM calls must degrade gracefully (retry, backoff, then a template fallback).
- Every graph step writes an audit record. No hidden behaviour.
- Speed matters: indexed queries, aggregation pipelines for metrics, parallel agents, no N+1 queries.

**In scope:** alert detection, case queue, two investigation agents (Profiler and Flow Analyst) plus a narrative writer and a critic, deterministic scoring and policy, action planner and mock executor, analyst approval (maker-checker for STR), audit trail, diagnostics, case report export, evals.

**Out of scope (state this in the README):** card fraud, account takeover, phishing, sanctions screening, real-time blocking, real bank integrations, real customer data.

**Done means:** one command seeds the database, one command starts the API and UI, all 40 planted alerts run end to end, and the eval page shows disposition accuracy and citation correctness.

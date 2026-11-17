/**
 * Display metadata shared by features: graph node order, agent colours, status
 * and disposition styling. Colours reference the design tokens so the same
 * colour means the same thing everywhere (stepper, logs, charts).
 */
import type { ActionStatus, AgentKind, CaseStatus, Disposition, NodeStatus } from "../types/api";

/** Graph nodes in execution order (graph/builder.py GRAPH_NODES). */
export const GRAPH_NODES: { node: string; agent: AgentKind; label: string }[] = [
  { node: "load_case", agent: "code", label: "Load case" },
  { node: "compute_metrics", agent: "code", label: "Compute metrics" },
  { node: "profiler", agent: "profiler", label: "Profiler" },
  { node: "flow_analyst", agent: "flow", label: "Flow analyst" },
  { node: "aggregate_evidence", agent: "code", label: "Aggregate evidence" },
  { node: "sufficiency_check", agent: "code", label: "Sufficiency check" },
  { node: "score_and_policy", agent: "code", label: "Score and policy" },
  { node: "plan_actions", agent: "code", label: "Plan actions" },
  { node: "narrative_writer", agent: "narrative", label: "Narrative writer" },
  { node: "critic", agent: "critic", label: "Critic" },
  { node: "analyst_gate", agent: "code", label: "Analyst gate" },
  { node: "apply_decision", agent: "code", label: "Apply decision" },
  { node: "execute_actions", agent: "code", label: "Execute actions" },
  { node: "finalize", agent: "code", label: "Finalize" },
];

export const AGENT_COLOR: Record<AgentKind, string> = {
  code: "var(--c-agent-code)",
  profiler: "var(--c-agent-profiler)",
  flow: "var(--c-agent-flow)",
  narrative: "var(--c-agent-narrative)",
  critic: "var(--c-agent-critic)",
};

export const AGENT_LABEL: Record<AgentKind, string> = {
  code: "Code",
  profiler: "Profiler",
  flow: "Flow analyst",
  narrative: "Narrative",
  critic: "Critic",
};

export const DISPOSITION_COLOR: Record<Disposition, string> = {
  close: "var(--c-risk-low)",
  escalate: "var(--c-risk-high)",
  str_draft: "var(--c-risk-critical)",
};

export const NODE_STATUS_COLOR: Record<NodeStatus, string> = {
  waiting: "var(--c-risk-medium)",
  running: "var(--c-accent)",
  done: "var(--c-risk-low)",
  fallback: "var(--c-risk-medium)",
  error: "var(--c-risk-critical)",
};

export const CASE_STATUS_COLOR: Record<CaseStatus, string> = {
  new: "var(--c-accent)",
  investigating: "var(--c-agent-profiler)",
  awaiting_decision: "var(--c-risk-medium)",
  closed: "var(--c-risk-low)",
  escalated: "var(--c-risk-high)",
  str_drafted: "var(--c-risk-critical)",
  returned: "var(--c-text-muted)",
};

export const ACTION_STATUS_COLOR: Record<ActionStatus, string> = {
  proposed: "var(--c-accent)",
  approved: "var(--c-agent-flow)",
  rejected: "var(--c-text-muted)",
  executed: "var(--c-risk-low)",
  completed: "var(--c-risk-low)",
  reversed: "var(--c-risk-medium)",
  cancelled: "var(--c-text-muted)",
};

export const ACTOR_COLOR: Record<string, string> = {
  system: "var(--c-agent-code)",
  agent: "var(--c-agent-narrative)",
  analyst: "var(--c-accent)",
};

/** Colour of an audit actor: agent nodes keep their own agent colour. */
export function actorColor(type: string, id: string): string {
  if (type === "agent") {
    const node = GRAPH_NODES.find((n) => n.node === id);
    if (node) return AGENT_COLOR[node.agent];
  }
  return ACTOR_COLOR[type] ?? "var(--c-text-secondary)";
}

/** Score to risk colour, matching the policy bands (40 / 70). */
export function scoreColor(score: number | null | undefined): string {
  if (score == null) return "var(--c-text-muted)";
  if (score >= 70) return "var(--c-risk-critical)";
  if (score >= 40) return "var(--c-risk-high)";
  if (score >= 35) return "var(--c-risk-medium)";
  return "var(--c-risk-low)";
}

/** Exit-speed colour for money-flow edges: fast exits are the risky ones. */
export function exitColor(minutes: number | null): string {
  if (minutes == null) return "var(--c-role-sender)";
  if (minutes < 30) return "var(--c-risk-critical)";
  if (minutes < 90) return "var(--c-risk-high)";
  if (minutes < 1440) return "var(--c-risk-medium)";
  return "var(--c-risk-low)";
}

export const SEVERITY_COLOR: Record<string, string> = {
  high: "var(--c-risk-critical)",
  medium: "var(--c-risk-high)",
  low: "var(--c-risk-medium)",
  info: "var(--c-text-muted)",
};

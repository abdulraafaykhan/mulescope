/**
 * API response types, hand-written in one file (by instruction, instead of
 * openapi-typescript, because most routes return plain dicts with no response
 * model). Shapes mirror the backend read models:
 *   - services/case_query.py (queue, detail, flow, timeline, transactions, summary, diagnostics)
 *   - repositories/mongo/* (`_id` -> `id`, Decimal128 -> number, account number masked)
 *   - graph/nodes/* (evidence, reports, actions, decisions documents)
 * Datetimes arrive as ISO-8601 UTC strings.
 */

export type IsoDate = string;

export type Disposition = "close" | "escalate" | "str_draft";
export type CaseStatus =
  | "new"
  | "investigating"
  | "awaiting_decision"
  | "closed"
  | "escalated"
  | "str_drafted"
  | "returned";
export type RunStatus = "running" | "awaiting_decision" | "completed" | "failed";
export type LlmMode = "live" | "fallback";
export type AgentKind = "code" | "profiler" | "flow" | "narrative" | "critic";
export type NodeStatus = "waiting" | "running" | "done" | "fallback" | "error";
export type ActionStatus =
  | "proposed"
  | "approved"
  | "rejected"
  | "executed"
  | "completed"
  | "reversed"
  | "cancelled";
export type DecisionKind = "approve" | "edit" | "override" | "request_more" | "reject";
export type Severity = "high" | "medium" | "low" | "info";

/** Loosely-typed JSON value used for free-form payloads (evidence data, audit payloads). */
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

export interface ApiErrorEnvelope {
  error: { code: string; message: string; detail: Json | null };
}

// --- system ------------------------------------------------------------------

export interface Health {
  status: string;
  db: string;
}

export interface PublicConfig {
  llm_mode: LlmMode;
  graph_version: string;
  config_versions: Record<string, string>;
  providers: Record<string, { configured: boolean; active: boolean }>;
  fallback_active: boolean;
}

// --- core entities -----------------------------------------------------------

export interface Kyc {
  name: string;
  dob: IsoDate | null;
  occupation: string;
  declared_income: number;
  pan_masked: string;
  city: string;
  kyc_status: string;
  kyc_refreshed_at: IsoDate | null;
}

export interface Customer {
  id: string;
  kyc: Kyc;
  risk_rating: string;
}

export interface Account {
  id: string;
  customer_id: string;
  account_no_masked: string;
  ifsc: string;
  type: string;
  status: string;
  opened_at: IsoDate;
  branch: string;
  holder_name: string;
  balance: number;
  declared_monthly_turnover: number | null;
  vpa?: string;
}

export interface Alert {
  id: string;
  account_id: string;
  rule_id: string;
  rule_version: string;
  window: { start: IsoDate; end: IsoDate };
  trigger_metrics: {
    inflow: number;
    outflow: number;
    pass_through: number;
    distinct_senders: number;
    credits: number;
    dormancy_days: number;
    rules_fired: string[];
  };
  priority: number;
  status: string;
  dedupe_key: string;
  created_at: IsoDate;
}

export interface Case {
  id: string;
  alert_id: string;
  account_id: string;
  status: CaseStatus;
  priority: number;
  assigned_to: string | null;
  sla_due_at: IsoDate | null;
  score: number | null;
  recommended_disposition: Disposition | null;
  final_disposition: Disposition | null;
  current_run_id: string | null;
  typologies?: string[];
  created_at: IsoDate;
  updated_at?: IsoDate;
}

export interface RunTotals {
  tokens: number;
  latency_ms: number;
  retries: number;
  fallback_nodes?: number;
}

export interface CaseRun {
  id: string;
  case_id: string;
  thread_id: string;
  graph_version: string;
  prompt_versions: Record<string, string>;
  models: Record<string, string>;
  dataset_seed: number | null;
  llm_mode: LlmMode;
  status: RunStatus;
  started_at: IsoDate;
  ended_at: IsoDate | null;
  totals: RunTotals;
  final_disposition?: Disposition | null;
  error?: string;
}

// --- queue -------------------------------------------------------------------

export interface QueueKpis {
  open_cases: number;
  sla_breaching: number;
  awaiting_decision: number;
  fallback_runs: number;
  total_cases: number;
}

export interface QueueRow {
  case_id: string;
  alert_id: string;
  account_id: string;
  account_masked: string | null;
  holder_name: string | null;
  customer_name: string | null;
  occupation: string | null;
  score: number | null;
  recommended_disposition: Disposition | null;
  final_disposition: Disposition | null;
  status: CaseStatus;
  priority: number;
  sla_due_at: IsoDate | null;
  assigned_to: string | null;
  inflow: number | null;
  senders: number | null;
  rule_id: string | null;
  created_at: IsoDate;
  current_run_id: string | null;
  run_status: RunStatus | null;
  llm_mode: LlmMode | null;
}

export interface Queue {
  kpis: QueueKpis;
  items: QueueRow[];
}

// --- case detail -------------------------------------------------------------

export interface PartyTop {
  ref: string;
  name: string;
  amount: number;
  count: number;
  type: string;
}

export interface EntityStrip {
  senders: { count: number; total: number; top: PartyTop[] };
  mule: {
    account_id: string;
    name: string;
    account_masked: string;
    occupation: string | null;
    declared_income: number | null;
    declared_monthly_turnover: number | null;
    window_inflow: number;
    opened_at: IsoDate | null;
    balance: number | null;
    kyc_status: string | null;
  };
  receivers: { count: number; total: number; channels: string[]; top: PartyTop[] };
}

export interface Decision {
  id: string;
  case_id: string;
  run_id: string;
  user_id: string;
  role: string;
  decision: DecisionKind;
  policy_disposition: Disposition;
  final_disposition: Disposition | null;
  override_reason: string | null;
  edits: Record<string, string>;
  created_at: IsoDate;
}

export interface CaseDetail {
  case: Case;
  alert: Alert;
  account: Account;
  customer: Customer;
  run: CaseRun | null;
  entity_strip: EntityStrip;
  decisions: Decision[];
}

// --- evidence, report, actions ----------------------------------------------

export interface Evidence {
  id: string;
  case_id: string;
  run_id: string;
  key: string;
  kind: string;
  source: string;
  statement: string;
  data: { [key: string]: Json };
  severity: Severity;
  refs: string[];
  cites: string[];
  created_at: IsoDate;
}

export interface CriticResult {
  verdict: "pass" | "revise";
  issues: string[];
  checks: string;
}

export interface Report {
  id: string;
  case_id: string;
  run_id: string;
  version: number;
  summary_md: string;
  str_narrative_md: string | null;
  customer_query_md: string | null;
  citations: string[];
  disposition_stated: Disposition;
  addressed_issues?: string[];
  critic: CriticResult | null;
  status: string;
  created_at: IsoDate;
}

export interface ActionHistory {
  ts: IsoDate;
  status: ActionStatus;
  by: string;
  reason?: string | null;
}

export interface Action {
  id: string;
  case_id: string;
  run_id: string;
  type: string;
  target: string;
  owner_role: string;
  due_in_days: number;
  requires_approval: boolean;
  reversible: boolean;
  mock_tool: string;
  params: { [key: string]: Json };
  description: string;
  rule: string;
  idempotency_key: string;
  status: ActionStatus;
  proposed_by: string;
  approved_by: string | null;
  due_at: IsoDate | null;
  executed_at: IsoDate | null;
  result: { mock_tool: string; ok: boolean; message: string } | null;
  evidence_ids: string[];
  history: ActionHistory[];
  created_at: IsoDate;
}

// --- flow, timeline, transactions -------------------------------------------

export type FlowRole = "mule" | "sender" | "receiver";

export interface FlowNode {
  id: string;
  role: FlowRole;
  label: string | null;
  sublabel: string | null;
  amount: number;
  count: number;
  ref?: string;
  balance?: number | null;
  opened_at?: IsoDate | null;
  first_ts?: IsoDate | null;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  amount: number;
  count: number;
  channel: string | null;
  exit_minutes: number | null;
}

export interface Flow {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface TimelineDay {
  date: string;
  inflow: number;
  outflow: number;
  credits: number;
  debits: number;
  balance: number | null;
}

export interface TimelineEvent {
  ts: IsoDate;
  direction: "credit" | "debit";
  amount: number;
  balance: number;
  channel: string;
}

export interface Timeline {
  days: TimelineDay[];
  events: TimelineEvent[];
}

export interface LedgerRow {
  id: string;
  transfer_id: string | null;
  account_id: string;
  direction: "credit" | "debit";
  amount: number;
  channel: string;
  ts: IsoDate;
  cp_type: string | null;
  cp_ref: string | null;
  cp_name: string | null;
  remarks: string | null;
  balance_after: number;
  evidence_ids?: string[];
}

export interface TransactionPage {
  items: LedgerRow[];
  next_cursor: string | null;
}

// --- account drawer ----------------------------------------------------------

export interface Complaint {
  id: string;
  victim_account_id: string;
  beneficiary_ref: string;
  linked_transfer_ids: string[];
  reported_at: IsoDate;
  amount: number;
  status: string;
}

export interface AccountSummary {
  account: Account;
  customer: Customer;
  baseline: {
    prior_weekly_inflow: number;
    prior_weekly_outflow: number;
    window_weekly_inflow: number;
    window_weekly_outflow: number;
  };
  balance_sparkline: { date: string; balance: number }[];
  complaints: Complaint[];
  cases: { case_id: string; status: CaseStatus; score: number | null }[];
  recent_transactions: LedgerRow[];
}

// --- audit, diagnostics ------------------------------------------------------

export interface AuditRecord {
  id: string;
  ts: IsoDate;
  actor: { type: "system" | "agent" | "analyst"; id: string };
  event: string;
  entity: { type: string; id: string };
  case_id: string | null;
  run_id: string | null;
  payload: { [key: string]: Json };
  prev_hash: string;
  hash: string;
}

export interface ChainVerification {
  case_id: string;
  valid: boolean;
  records: number;
  head?: string;
  broken_at?: string;
}

export interface NodeExecution {
  id: string;
  run_id: string;
  case_id: string;
  node: string;
  agent: AgentKind;
  status: NodeStatus;
  started_at: IsoDate;
  ended_at?: IsoDate;
  latency_ms: number | null;
  tokens_in: number;
  tokens_out: number;
  retries: number;
  fallback_used: boolean;
  cache_hit?: boolean;
  prompt_version?: string | null;
  model?: string | null;
  output_summary?: string | null;
  tool_calls?: Json[];
  error?: string;
}

export interface Diagnostics {
  run: CaseRun;
  nodes: NodeExecution[];
  tokens_by_agent: Record<string, number>;
  fallback_used: boolean;
  total_latency_ms: number;
}

// --- SSE events (graph/instrument.py, services/case_runner.py) --------------

export interface NodeEvent {
  type: "node";
  node: string;
  agent: AgentKind;
  status: NodeStatus;
  message: string;
  tokens: number;
  latency_ms?: number;
}

export interface InterruptEvent {
  type: "interrupt";
  node: "analyst_gate";
  status: "waiting";
  payload: { case_id: string; run_id: string; disposition: Disposition; score: number; report_id: string; actions: string[] };
}

export interface RunCompletedEvent {
  type: "run_completed";
  status: "completed";
  final_disposition: Disposition | null;
}

export interface RunFailedEvent {
  type: "run_failed";
  status: "failed";
  message: string;
}

export type RunEvent = NodeEvent | InterruptEvent | RunCompletedEvent | RunFailedEvent;

// --- requests ----------------------------------------------------------------

export interface DecisionRequest {
  decision: DecisionKind;
  user_id?: string;
  role?: "analyst" | "senior_reviewer";
  reason?: string | null;
  override_disposition?: Disposition | null;
  edits?: Record<string, string> | null;
}

export interface ActionPatch {
  op: "approve" | "reject" | "reverse";
  user_id?: string;
  reason?: string | null;
}

// --- evals (written by `uv run evals`, read by GET /evals/runs) -------------

export interface EvalMetrics {
  total: number;
  evaluated: number;
  correct: number;
  accuracy: number;
  mules_closed: number;
  confusion: Record<Disposition, Record<Disposition, number>>;
  citation_validity: number;
  claim_coverage: number;
  tipping_off_violations: number;
  injection_obeyed: number;
  fallback_rate: number;
  latency_ms_p50: number;
  latency_ms_p95: number;
  tokens_total: number;
  tokens_per_case: number;
}

export interface EvalRun {
  id: string;
  mode: LlmMode;
  status: "running" | "completed";
  dataset_seed: number | null;
  policy_version: string;
  graph_version: string;
  started_at: IsoDate;
  ended_at: IsoDate | null;
  metrics: EvalMetrics | null;
  created_at: IsoDate;
}

export interface EvalResult {
  id: string;
  run_id: string;
  case_id: string;
  account_id: string;
  scenario_type: string;
  label: string;
  expected: Disposition;
  predicted: Disposition | null;
  correct: boolean;
  score: number | null;
  citations: number;
  invalid_citations: number;
  claim_coverage: number;
  tipping_off: boolean;
  fallback_nodes: number;
  latency_ms: number;
  tokens: number;
  error?: string | null;
}

export interface EvalRunDetail {
  run: EvalRun;
  results: EvalResult[];
}

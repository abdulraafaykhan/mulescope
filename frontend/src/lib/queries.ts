/**
 * TanStack Query hooks: one per API resource. Presentational components never
 * fetch; feature containers call these hooks and pass data down.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type {
  Action,
  ActionPatch,
  AccountSummary,
  AuditRecord,
  CaseDetail,
  ChainVerification,
  DecisionRequest,
  Diagnostics,
  EvalRun,
  EvalRunDetail,
  Evidence,
  Flow,
  ObservabilityPeriod,
  ObservabilitySummary,
  ObservedRun,
  PublicConfig,
  RunObservability,
  Queue,
  Report,
  Timeline,
  TransactionPage,
} from "../types/api";

export const keys = {
  config: ["config"] as const,
  queue: (status: string, priority: string) => ["queue", status, priority] as const,
  caseRoot: (id: string) => ["case", id] as const,
  case: (id: string) => ["case", id, "detail"] as const,
  evidence: (id: string) => ["case", id, "evidence"] as const,
  report: (id: string) => ["case", id, "report"] as const,
  actions: (id: string) => ["case", id, "actions"] as const,
  flow: (id: string) => ["case", id, "flow"] as const,
  timeline: (id: string) => ["case", id, "timeline"] as const,
  transactions: (id: string, cursor: string | null) => ["case", id, "transactions", cursor] as const,
  audit: (id: string) => ["case", id, "audit"] as const,
  verify: (id: string) => ["case", id, "verify"] as const,
  diagnostics: (runId: string) => ["run", runId, "diagnostics"] as const,
  account: (id: string) => ["account", id] as const,
  evalRuns: ["evals"] as const,
  evalRun: (id: string) => ["evals", id] as const,
  obsSummary: (period: ObservabilityPeriod) => ["observability", "summary", period] as const,
  obsRuns: (period: ObservabilityPeriod) => ["observability", "runs", period] as const,
  obsRun: (runId: string) => ["observability", "run", runId] as const,
};

const ACTIVE_POLL_MS = 3000;
// The free-tier watch looks at the last minute, so the summary refreshes often.
const OBSERVABILITY_POLL_MS = 15_000;

export function usePublicConfig() {
  return useQuery({ queryKey: keys.config, queryFn: () => api.get<PublicConfig>("/config/public"), staleTime: 60_000 });
}

export function useQueue(status: string, priority: string) {
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  if (priority) qs.set("priority", priority);
  return useQuery({
    queryKey: keys.queue(status, priority),
    queryFn: () => api.get<Queue>(`/cases${qs.size ? `?${qs.toString()}` : ""}`),
    refetchInterval: 15_000,
  });
}

export function useCase(caseId: string) {
  return useQuery({
    queryKey: keys.case(caseId),
    queryFn: () => api.get<CaseDetail>(`/cases/${caseId}`),
    // Polling while a run is active is the safety net for a silent SSE drop.
    refetchInterval: (q) => (q.state.data?.run?.status === "running" ? ACTIVE_POLL_MS : false),
  });
}

export function useEvidence(caseId: string) {
  return useQuery({ queryKey: keys.evidence(caseId), queryFn: () => api.get<Evidence[]>(`/cases/${caseId}/evidence`) });
}

export function useReport(caseId: string, enabled: boolean) {
  return useQuery({ queryKey: keys.report(caseId), queryFn: () => api.get<Report>(`/cases/${caseId}/report`), enabled, retry: false });
}

export function useActions(caseId: string) {
  return useQuery({ queryKey: keys.actions(caseId), queryFn: () => api.get<Action[]>(`/cases/${caseId}/actions`) });
}

export function useFlow(caseId: string) {
  return useQuery({ queryKey: keys.flow(caseId), queryFn: () => api.get<Flow>(`/cases/${caseId}/flow`), staleTime: Infinity });
}

export function useTimeline(caseId: string) {
  return useQuery({ queryKey: keys.timeline(caseId), queryFn: () => api.get<Timeline>(`/cases/${caseId}/timeline`), staleTime: Infinity });
}

export function useTransactions(caseId: string, cursor: string | null) {
  const qs = new URLSearchParams({ limit: "200" });
  if (cursor) qs.set("cursor", cursor);
  return useQuery({ queryKey: keys.transactions(caseId, cursor), queryFn: () => api.get<TransactionPage>(`/cases/${caseId}/transactions?${qs.toString()}`) });
}

export function useAudit(caseId: string) {
  return useQuery({ queryKey: keys.audit(caseId), queryFn: () => api.get<AuditRecord[]>(`/audit?case_id=${encodeURIComponent(caseId)}&limit=500`) });
}

export function useChainVerify(caseId: string) {
  return useQuery({ queryKey: keys.verify(caseId), queryFn: () => api.get<ChainVerification>(`/cases/${caseId}/audit/verify`) });
}

export function useDiagnostics(runId: string | null | undefined, active: boolean) {
  return useQuery({
    queryKey: keys.diagnostics(runId ?? "none"),
    queryFn: () => api.get<Diagnostics>(`/runs/${runId}/diagnostics`),
    enabled: Boolean(runId),
    refetchInterval: active ? ACTIVE_POLL_MS : false,
  });
}

export function useAccountSummary(accountId: string | null) {
  return useQuery({
    queryKey: keys.account(accountId ?? "none"),
    queryFn: () => api.get<AccountSummary>(`/accounts/${accountId}/summary`),
    enabled: Boolean(accountId),
    staleTime: 60_000,
  });
}

export function useEvalRuns() {
  return useQuery({ queryKey: keys.evalRuns, queryFn: () => api.get<EvalRun[]>("/evals/runs") });
}

export function useEvalRun(runId: string | null) {
  return useQuery({ queryKey: keys.evalRun(runId ?? "none"), queryFn: () => api.get<EvalRunDetail>(`/evals/runs/${runId}`), enabled: Boolean(runId) });
}

export function useObservabilitySummary(period: ObservabilityPeriod) {
  return useQuery({ queryKey: keys.obsSummary(period), queryFn: () => api.get<ObservabilitySummary>(`/observability/summary?period=${period}`), refetchInterval: OBSERVABILITY_POLL_MS });
}

export function useObservedRuns(period: ObservabilityPeriod) {
  return useQuery({ queryKey: keys.obsRuns(period), queryFn: () => api.get<ObservedRun[]>(`/observability/runs?period=${period}&limit=100`), refetchInterval: OBSERVABILITY_POLL_MS });
}

export function useObservedRun(runId: string | null | undefined, active = false) {
  return useQuery({
    queryKey: keys.obsRun(runId ?? "none"),
    queryFn: () => api.get<RunObservability>(`/observability/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: active ? ACTIVE_POLL_MS : false,
  });
}

/** Refetch everything that belongs to one case (after a run event or decision). */
export function useInvalidateCase() {
  const qc = useQueryClient();
  return (caseId: string) => {
    void qc.invalidateQueries({ queryKey: keys.caseRoot(caseId) });
    void qc.invalidateQueries({ queryKey: ["run"] });
    void qc.invalidateQueries({ queryKey: ["queue"] });
  };
}

export function useStartRun(caseId: string) {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: () => api.post<{ run_id: string; status: string }>(`/cases/${caseId}/runs`),
    onSuccess: () => invalidate(caseId),
  });
}

export function useDecision(caseId: string) {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: (body: DecisionRequest) => api.post<{ run_id: string; status: string }>(`/cases/${caseId}/decision`, body),
    onSuccess: () => invalidate(caseId),
  });
}

export function usePatchAction(caseId: string) {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ActionPatch }) => api.patch<Action>(`/actions/${id}`, body),
    onSuccess: () => invalidate(caseId),
  });
}

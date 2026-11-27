/**
 * Diagnostics of the current run: summary tiles (including the estimated LLM
 * cost from the observability log), a latency waterfall per node, the model,
 * prompt and tokens of each agent, run metadata and a link to every LLM
 * attempt of the run on the Observability page. Template
 * fallbacks are summarised in one line with their reasons on demand. The
 * layout reflows with the drawer width (container queries), so nothing
 * overlaps when the drawer is narrow or short. Reads `GET /runs/{run_id}/diagnostics`.
 */
import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { useDiagnostics, useObservedRun } from "../../lib/queries";
import { Empty, ErrorState, Fact, SkeletonRows } from "../../components/ui/primitives";
import { AGENT_COLOR, AGENT_LABEL, GRAPH_NODES, NODE_STATUS_COLOR } from "../../lib/meta";
import type { AgentKind, CaseRun, Diagnostics, NodeExecution } from "../../types/api";
import { humanize, int, ms, usd } from "../../lib/format";

/** `case_runs.models` keys -> agent colour key used by node executions. */
const MODEL_AGENT: Record<string, AgentKind> = { profiler: "profiler", flow_analyst: "flow", narrative: "narrative", critic: "critic" };
const NODE_LABEL = new Map(GRAPH_NODES.map((n) => [n.node, n.label]));
const MIN_BAR_PCT = 0.8;

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="mb-2 text-xs font-semibold tracking-wide text-secondary uppercase">{children}</h3>;
}

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-elevated/40 px-3 py-2">
      <div className="truncate text-[11px] text-muted uppercase">{label}</div>
      <div className="num truncate text-base font-semibold text-primary">{value}</div>
      {hint && <div className="truncate text-[11px] text-muted">{hint}</div>}
    </div>
  );
}

function FallbackNotice({ nodes, mode }: { nodes: NodeExecution[]; mode: string }) {
  const fell = nodes.filter((n) => n.fallback_used);
  const reasons = fell.filter((n) => n.fallback_reason);
  return (
    <details className="shrink-0 border-b border-risk-medium/40 bg-risk-medium/10 px-3 py-1.5 text-xs text-risk-medium" role="status">
      <summary className="flex cursor-pointer items-center gap-2">
        <AlertTriangle size={13} aria-hidden />
        {fell.length} step(s) used the template fallback (LLM mode {mode}){reasons.length > 0 && " · show reasons"}
      </summary>
      {reasons.length > 0 && (
        <ul className="mt-1 max-h-28 space-y-0.5 overflow-y-auto pl-5">
          {reasons.map((n) => <li key={n.id} className="num break-words"><span className="font-semibold">{n.node}:</span> {n.fallback_reason}</li>)}
        </ul>
      )}
    </details>
  );
}

function Waterfall({ nodes }: { nodes: NodeExecution[] }) {
  const t0 = Math.min(...nodes.map((n) => new Date(n.started_at).getTime()));
  const tEnd = Math.max(...nodes.map((n) => new Date(n.started_at).getTime() + (n.latency_ms ?? 0)));
  const span = Math.max(1, tEnd - t0);
  return (
    <ul className="space-y-1">
      {nodes.map((n) => {
        const left = ((new Date(n.started_at).getTime() - t0) / span) * 100;
        const width = Math.max(MIN_BAR_PCT, ((n.latency_ms ?? 0) / span) * 100);
        return (
          <li key={n.id} title={n.fallback_reason ?? n.error ?? n.output_summary ?? undefined} className="grid grid-cols-[minmax(96px,150px)_minmax(0,1fr)_64px] items-center gap-2 text-xs">
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: NODE_STATUS_COLOR[n.status] }} aria-label={n.status} />
              <span className="truncate text-secondary">{NODE_LABEL.get(n.node) ?? n.node}</span>
            </span>
            <span className="relative h-3 rounded bg-elevated">
              <span className="absolute top-0 h-full rounded" style={{ left: `${Math.min(left, 100 - width)}%`, width: `${width}%`, background: AGENT_COLOR[n.agent], opacity: n.fallback_used ? 0.55 : 1 }} />
            </span>
            <span className="num text-right text-muted">{ms(n.latency_ms)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function AgentTable({ run, tokens }: { run: CaseRun; tokens: Record<string, number> }) {
  return (
    <table className="w-full table-fixed text-xs">
      <thead className="text-left text-muted">
        <tr><th className="w-[30%] pb-1 font-normal">Agent</th><th className="pb-1 font-normal">Model · prompt</th><th className="w-16 pb-1 text-right font-normal">Tokens</th></tr>
      </thead>
      <tbody>
        {Object.entries(run.models).map(([key, model]) => {
          const agent = MODEL_AGENT[key];
          return (
            <tr key={key} className="border-t border-line/50 align-top">
              <td className="py-1 pr-2" style={{ color: agent ? AGENT_COLOR[agent] : undefined }}>{agent ? AGENT_LABEL[agent] : humanize(key)}</td>
              <td className="num min-w-0 py-1 pr-2 break-all text-secondary">{model}<span className="block text-muted">{run.prompt_versions[key] ?? "—"}</span></td>
              <td className="num py-1 text-right text-primary">{int(agent ? (tokens[agent] ?? 0) : 0)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Body({ data, active }: { data: Diagnostics; active: boolean }) {
  const { run, nodes, tokens_by_agent: tokens, total_latency_ms: total } = data;
  const observed = useObservedRun(run.id, active);
  const wall = run.ended_at ? new Date(run.ended_at).getTime() - new Date(run.started_at).getTime() : null;
  const live = nodes.filter((n) => n.agent !== "code" && !n.fallback_used);
  const tokenSum = Object.values(tokens).reduce((s, n) => s + n, 0);
  const llm = observed.data?.run.llm;
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-3">
      <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4 @5xl:grid-cols-7">
        <Stat label="Run wall time" value={ms(wall)} hint={run.ended_at ? undefined : humanize(run.status)} />
        <Stat label="Node time" value={ms(total)} hint={`${nodes.length} steps`} />
        <Stat label="Tokens" value={int(tokenSum)} />
        <Stat label="Estimated cost" value={usd(llm?.cost_usd)} hint={llm ? `${llm.attempts} attempts · list price` : undefined} />
        <Stat label="LLM calls" value={live.length} hint={live.length ? `${live.filter((n) => n.cache_hit).length} cache hits` : "no live calls"} />
        <Stat label="Retries" value={nodes.reduce((s, n) => s + n.retries, 0)} />
        <Stat label="Failures" value={nodes.filter((n) => n.status === "error").length} />
      </div>
      <div className="mt-4 grid gap-5 @4xl:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
        <section className="min-w-0">
          <SectionTitle>Latency waterfall</SectionTitle>
          {nodes.length ? <Waterfall nodes={nodes} /> : <p className="text-xs text-muted">No steps recorded yet.</p>}
        </section>
        <div className="min-w-0 space-y-4">
          <section>
            <SectionTitle>Agents</SectionTitle>
            <AgentTable run={run} tokens={tokens} />
          </section>
          <section>
            <div className="flex items-baseline justify-between gap-2">
              <SectionTitle>Run</SectionTitle>
              <Link to={`/observability?period=all&run=${run.id}`} className="flex items-center gap-1 text-xs text-accent hover:underline">
                Every LLM attempt <ExternalLink size={11} aria-hidden />
              </Link>
            </div>
            <Fact label="Run" mono>{run.id}</Fact>
            <Fact label="Status">{humanize(run.status)}</Fact>
            <Fact label="LLM mode">{run.llm_mode}</Fact>
            <Fact label="Graph version" mono>{run.graph_version}</Fact>
            <Fact label="Dataset seed" mono>{run.dataset_seed ?? "—"}</Fact>
          </section>
        </div>
      </div>
    </div>
  );
}

export function DiagnosticsView({ runId, runActive }: { runId: string | null; runActive: boolean }) {
  const diag = useDiagnostics(runId, runActive);
  if (!runId) return <Empty>No run yet.</Empty>;
  if (diag.isLoading) return <SkeletonRows rows={6} />;
  if (diag.isError) return <ErrorState error={diag.error} />;
  if (!diag.data) return null;
  return (
    <div className="@container flex h-full flex-col">
      {diag.data.fallback_used && <FallbackNotice nodes={diag.data.nodes} mode={diag.data.run.llm_mode} />}
      <Body data={diag.data} active={runActive} />
    </div>
  );
}

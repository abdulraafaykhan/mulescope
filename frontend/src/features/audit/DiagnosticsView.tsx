/**
 * Diagnostics of the current run: fallback banner, latency waterfall per node,
 * tokens by agent, retries and failures, LLM mode, models, versions, seed and
 * total run time. Reads `GET /runs/{run_id}/diagnostics`.
 */
import { AlertTriangle } from "lucide-react";
import { useDiagnostics } from "../../lib/queries";
import { Empty, ErrorState, Fact, SkeletonRows } from "../../components/ui/primitives";
import { AGENT_COLOR, AGENT_LABEL } from "../../lib/meta";
import type { AgentKind } from "../../types/api";
import { int, ms } from "../../lib/format";

export function DiagnosticsView({ runId, runActive }: { runId: string | null; runActive: boolean }) {
  const diag = useDiagnostics(runId, runActive);
  if (!runId) return <Empty>No run yet.</Empty>;
  if (diag.isLoading) return <SkeletonRows rows={6} />;
  if (diag.isError) return <ErrorState error={diag.error} />;
  if (!diag.data) return null;
  const { run, nodes, tokens_by_agent: tokens, fallback_used: fallback, total_latency_ms: total } = diag.data;
  const t0 = nodes.length ? Math.min(...nodes.map((n) => new Date(n.started_at).getTime())) : 0;
  const tEnd = nodes.length ? Math.max(...nodes.map((n) => new Date(n.started_at).getTime() + (n.latency_ms ?? 0))) : 1;
  const span = Math.max(1, tEnd - t0);
  const retries = nodes.reduce((s, n) => s + n.retries, 0);
  const errors = nodes.filter((n) => n.status === "error").length;
  const reasons = nodes.filter((n) => n.fallback_reason);
  const llmNodes = nodes.filter((n) => n.agent !== "code" && !n.fallback_used);
  const wall = run.ended_at ? new Date(run.ended_at).getTime() - new Date(run.started_at).getTime() : null;

  return (
    <div className="flex h-full flex-col">
      {fallback && (
        <div className="shrink-0 border-b border-risk-medium/40 bg-risk-medium/10 px-3 py-1.5 text-xs text-risk-medium" role="status">
          <div className="flex items-center gap-2">
            <AlertTriangle size={13} aria-hidden /> {nodes.filter((n) => n.fallback_used).length} node(s) used the template fallback (LLM mode {run.llm_mode}).
          </div>
          {reasons.length > 0 && (
            <ul className="mt-1 space-y-0.5 pl-5">
              {reasons.map((n) => <li key={n.id} className="num break-words"><span className="font-semibold">{n.node}:</span> {n.fallback_reason}</li>)}
            </ul>
          )}
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_280px_280px] gap-4 overflow-hidden p-3">
        <div className="min-h-0 overflow-y-auto">
          <div className="mb-1 text-xs font-semibold text-secondary uppercase">Latency waterfall</div>
          <ul className="space-y-0.5">
            {nodes.map((n) => {
              const left = ((new Date(n.started_at).getTime() - t0) / span) * 100;
              const width = Math.max(0.6, ((n.latency_ms ?? 0) / span) * 100);
              return (
                <li key={n.id} title={n.fallback_reason ?? undefined} className="grid grid-cols-[130px_1fr_64px] items-center gap-2 text-[11px]">
                  <span className="truncate text-secondary">{n.node}</span>
                  <span className="relative h-2.5 rounded bg-elevated">
                    <span className="absolute top-0 h-full rounded" style={{ left: `${left}%`, width: `${width}%`, background: AGENT_COLOR[n.agent], opacity: n.fallback_used ? 0.6 : 1 }} />
                  </span>
                  <span className="num text-right text-muted">{ms(n.latency_ms)}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <div className="min-h-0 overflow-y-auto">
          <div className="mb-1 text-xs font-semibold text-secondary uppercase">Tokens by agent</div>
          {Object.entries(tokens).map(([agent, n]) => (
            <Fact key={agent} label={AGENT_LABEL[agent as AgentKind] ?? agent} mono>
              <span style={{ color: AGENT_COLOR[agent as AgentKind] }}>{int(n)}</span>
            </Fact>
          ))}
          <div className="mt-2 border-t border-line pt-2">
            <Fact label="Node time (sum)" mono>{ms(total)}</Fact>
            <Fact label="Run wall time" mono>{ms(wall)}</Fact>
            <Fact label="Retries" mono>{retries}</Fact>
            <Fact label="Failures" mono>{errors}</Fact>
            <Fact label="Cache hit rate" mono>{llmNodes.length ? `${llmNodes.filter((n) => n.cache_hit).length} / ${llmNodes.length} LLM calls` : "n/a (no LLM calls)"}</Fact>
          </div>
        </div>
        <div className="min-h-0 overflow-y-auto">
          <div className="mb-1 text-xs font-semibold text-secondary uppercase">Run</div>
          <Fact label="Run" mono>{run.id}</Fact>
          <Fact label="Status">{run.status}</Fact>
          <Fact label="LLM mode">{run.llm_mode}</Fact>
          <Fact label="Graph version" mono>{run.graph_version}</Fact>
          <Fact label="Dataset seed" mono>{run.dataset_seed ?? "—"}</Fact>
          {Object.entries(run.models).map(([a, m]) => <Fact key={a} label={`model · ${a}`} mono>{m}</Fact>)}
          {Object.entries(run.prompt_versions).map(([a, v]) => <Fact key={a} label={`prompt · ${a}`} mono>{v}</Fact>)}
        </div>
      </div>
    </div>
  );
}

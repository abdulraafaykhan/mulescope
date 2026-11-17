/**
 * Agents panel: live stepper of the graph, one row per node in graph order,
 * coloured by agent. Status comes from live SSE events layered over the
 * persisted node_executions (diagnostics), so a dropped stream or an API
 * restart never leaves the stepper stale. Expand a row for its details.
 */
import { useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Circle, Hourglass, Loader2, XCircle } from "lucide-react";
import type { CaseRun, NodeExecution, NodeStatus, RunEvent } from "../../types/api";
import type { StreamState } from "../../lib/useRunStream";
import { useDiagnostics } from "../../lib/queries";
import { Panel } from "../../components/ui/primitives";
import { Chip } from "../../components/ui/chips";
import { AGENT_COLOR, AGENT_LABEL, GRAPH_NODES, NODE_STATUS_COLOR } from "../../lib/meta";
import { int, ms } from "../../lib/format";

interface Row {
  status: NodeStatus | "pending";
  message: string | null;
  latency: number | null;
  tokens: number;
  exec: NodeExecution | null;
}

const ICON: Record<Row["status"], ReactNode> = {
  pending: <Circle size={13} aria-hidden />,
  waiting: <Hourglass size={13} aria-hidden />,
  running: <Loader2 size={13} className="animate-spin" aria-hidden />,
  done: <CheckCircle2 size={13} aria-hidden />,
  fallback: <AlertTriangle size={13} aria-hidden />,
  error: <XCircle size={13} aria-hidden />,
};

function buildRows(execs: NodeExecution[], events: RunEvent[]): Map<string, Row> {
  const rows = new Map<string, Row>();
  for (const e of execs) {
    rows.set(e.node, { status: e.status, message: e.output_summary ?? e.error ?? null, latency: e.latency_ms, tokens: e.tokens_in + e.tokens_out, exec: e });
  }
  for (const ev of events) {
    if (ev.type !== "node") continue;
    const prev = rows.get(ev.node);
    rows.set(ev.node, { status: ev.status, message: ev.message, latency: ev.latency_ms ?? (ev.status === "running" ? null : prev?.latency ?? null), tokens: ev.tokens || prev?.tokens || 0, exec: prev?.exec ?? null });
  }
  return rows;
}

function Details({ exec }: { exec: NodeExecution | null }) {
  if (!exec) return <div className="px-3 pb-2 text-xs text-muted">Details appear once the node finishes.</div>;
  return (
    <div className="space-y-1 px-3 pb-2 text-xs">
      {exec.output_summary && <div className="text-secondary">{exec.output_summary}</div>}
      <div className="num grid grid-cols-2 gap-x-3 text-muted">
        <span>model {exec.model ?? "—"}</span>
        <span>prompt {exec.prompt_version ?? "—"}</span>
        <span>tokens in {int(exec.tokens_in)} / out {int(exec.tokens_out)}</span>
        <span>retries {exec.retries}</span>
      </div>
      {exec.tool_calls && exec.tool_calls.length > 0 && (
        <details className="text-muted">
          <summary className="cursor-pointer">{exec.tool_calls.length} tool call(s)</summary>
          <pre className="num mt-1 max-h-40 overflow-auto rounded bg-app p-2 text-[11px]">{JSON.stringify(exec.tool_calls, null, 2)}</pre>
        </details>
      )}
      {exec.error && <div className="text-risk-critical">{exec.error}</div>}
    </div>
  );
}

export function AgentsPanel({ run, events, streamState }: { run: CaseRun | null; events: RunEvent[]; streamState: StreamState }) {
  const active = run?.status === "running";
  const diag = useDiagnostics(run?.id, active);
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => buildRows(diag.data?.nodes ?? [], events), [diag.data, events]);
  const fallback = [...rows.values()].some((r) => r.status === "fallback");
  const failed = events.find((e) => e.type === "run_failed");

  return (
    <Panel
      title="Agents"
      actions={
        <div className="flex items-center gap-1.5">
          {fallback && <Chip color="var(--c-risk-medium)" icon={<AlertTriangle size={11} aria-hidden />} title="At least one node used its template fallback">fallback</Chip>}
          {run && <span className="num text-xs text-muted">{streamState === "reconnecting" ? "reconnecting…" : run.status.replace("_", " ")}</span>}
        </div>
      }
    >
      {!run && <p className="p-3 text-sm text-muted">Start an investigation to watch the agents work.</p>}
      {run && (
        <ol>
          {GRAPH_NODES.map((n) => {
            const row = rows.get(n.node) ?? { status: "pending" as const, message: null, latency: null, tokens: 0, exec: null };
            const color = AGENT_COLOR[n.agent];
            const statusColor = row.status === "pending" ? "var(--c-text-muted)" : NODE_STATUS_COLOR[row.status];
            const expanded = open === n.node;
            return (
              <li key={n.node} className="border-b border-line/60 last:border-0" style={{ boxShadow: `inset 3px 0 0 ${color}` }}>
                <button type="button" onClick={() => setOpen(expanded ? null : n.node)} aria-expanded={expanded} className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-elevated">
                  {expanded ? <ChevronDown size={12} className="text-muted" aria-hidden /> : <ChevronRight size={12} className="text-muted" aria-hidden />}
                  <span className={`flex h-5 w-5 items-center justify-center rounded-full ${row.status === "running" ? "pulse-dot" : ""}`} style={{ color: statusColor }}>
                    {ICON[row.status]}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-sm">
                      <span className={row.status === "pending" ? "text-muted" : "text-primary"}>{n.label}</span>
                      {n.agent !== "code" && <span className="rounded px-1 text-[10px] font-semibold uppercase" style={{ color, background: `color-mix(in srgb, ${color} 15%, transparent)` }}>{AGENT_LABEL[n.agent]}</span>}
                    </span>
                    {row.message && row.status !== "pending" && <span className="block truncate text-[11px] text-muted" title={row.message}>{row.message}</span>}
                  </span>
                  <span className="num shrink-0 text-right text-[11px] text-muted">
                    <span className="block" style={{ color: statusColor }}>{row.status}</span>
                    {row.latency != null && <span className="block">{ms(row.latency)}{row.tokens ? ` · ${int(row.tokens)} tok` : ""}</span>}
                  </span>
                </button>
                {expanded && <Details exec={row.exec} />}
              </li>
            );
          })}
        </ol>
      )}
      {run?.status === "awaiting_decision" && <div className="border-t border-line bg-risk-medium/10 px-3 py-2 text-xs text-risk-medium">Waiting at the analyst gate. Review the report and actions, then decide in the header.</div>}
      {(failed || run?.status === "failed") && <div role="alert" className="border-t border-line bg-risk-critical/10 px-3 py-2 text-xs text-risk-critical">Run failed: {failed && failed.type === "run_failed" ? failed.message : run?.error}</div>}
    </Panel>
  );
}

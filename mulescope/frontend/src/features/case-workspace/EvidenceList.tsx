/**
 * Evidence ledger of the current run, filterable by kind and source. Click an
 * item to highlight it everywhere it is cited.
 */
import { useMemo, useState } from "react";
import type { Evidence } from "../../types/api";
import { Empty, Panel, SkeletonRows } from "../../components/ui/primitives";
import { SEVERITY_COLOR } from "../../lib/meta";
import { useEvidenceCtx } from "./EvidenceContext";

export function EvidenceList({ evidence, loading, hasRun }: { evidence: Evidence[]; loading: boolean; hasRun: boolean }) {
  const { highlighted, highlight } = useEvidenceCtx();
  const [kind, setKind] = useState("");
  const [source, setSource] = useState("");
  const kinds = useMemo(() => [...new Set(evidence.map((e) => e.kind))].sort(), [evidence]);
  const sources = useMemo(() => [...new Set(evidence.map((e) => e.source))].sort(), [evidence]);
  const rows = evidence.filter((e) => (!kind || e.kind === kind) && (!source || e.source === source));
  const select = "h-7 min-w-0 flex-1 rounded-md border border-line bg-elevated px-1 text-xs text-primary";

  return (
    <Panel title={`Evidence (${evidence.length})`} className="flex min-h-[240px] flex-1 flex-col" bodyClass="flex min-h-0 flex-1 flex-col">
      <div className="flex gap-2 border-b border-line p-2">
        <select aria-label="Filter by kind" value={kind} onChange={(e) => setKind(e.target.value)} className={select}>
          <option value="">All kinds</option>
          {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <select aria-label="Filter by source" value={source} onChange={(e) => setSource(e.target.value)} className={select}>
          <option value="">All sources</option>
          {sources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && <SkeletonRows rows={6} />}
        {!loading && !hasRun && <Empty>No run yet. Evidence appears as the agents work.</Empty>}
        {!loading && hasRun && rows.length === 0 && <Empty>No evidence for these filters yet.</Empty>}
        <ul>
          {rows.map((e) => (
            <li key={e.id} id={`evd-${e.id}`}>
              <button
                type="button"
                onClick={() => highlight(highlighted === e.id ? null : e.id)}
                className={`block w-full border-b border-line/60 px-3 py-2 text-left transition hover:bg-elevated ${highlighted === e.id ? "bg-accent/10 ring-1 ring-accent ring-inset" : ""}`}
              >
                <span className="mb-0.5 flex items-center justify-between text-[11px]">
                  <span className="num text-accent">{e.id}</span>
                  <span className="flex items-center gap-1 text-muted">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[e.severity] }} aria-hidden />
                    {e.severity} · {e.kind}
                  </span>
                </span>
                <span className="block text-xs leading-snug text-secondary">{e.statement}</span>
                {e.cites.length > 0 && <span className="num mt-0.5 block text-[11px] text-muted">cites {e.cites.join(", ")}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

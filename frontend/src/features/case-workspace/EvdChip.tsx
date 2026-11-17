/**
 * `EVD-` citation chip with a hover card showing the evidence statement. Click
 * jumps to the item in the evidence list.
 *
 * Three states:
 * - in the current run's ledger: accent colour, hover shows the statement;
 * - not in the current ledger, but cited by a record of an earlier run
 *   (`originRunId` differs from the current run): neutral, "from an earlier
 *   run". Executed actions keep the evidence ids of the run that proposed them;
 * - anything else: red, a citation that points at nothing.
 */
import { useState } from "react";
import { SEVERITY_COLOR } from "../../lib/meta";
import { useEvidenceCtx } from "./EvidenceContext";

type ChipState = "current" | "earlier" | "unknown";

const STATE_COLOR: Record<ChipState, string> = {
  current: "var(--c-accent)",
  earlier: "var(--c-text-muted)",
  unknown: "var(--c-risk-critical)",
};

export function EvdChip({ id, originRunId }: { id: string; originRunId?: string | null }) {
  const { byId, runId, highlighted, jumpTo } = useEvidenceCtx();
  const [hover, setHover] = useState(false);
  const ev = byId.get(id);
  const state: ChipState = ev ? "current" : originRunId && runId && originRunId !== runId ? "earlier" : "unknown";
  const active = highlighted === id;
  const color = STATE_COLOR[state];
  const label =
    state === "current" ? `Evidence ${id}: ${ev?.statement ?? ""}` : state === "earlier" ? `Evidence ${id}, from an earlier run (${originRunId})` : `Unknown evidence ${id}`;
  return (
    <span className="relative inline-block align-baseline" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button
        type="button"
        onClick={() => state === "current" && jumpTo(id)}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        title={state === "earlier" ? "from an earlier run" : undefined}
        className={`num mx-0.5 rounded border px-1 text-[11px] leading-4 ${state === "earlier" ? "border-dashed" : ""}`}
        style={{ color, borderColor: `color-mix(in srgb, ${color} ${active ? 90 : 40}%, transparent)`, background: `color-mix(in srgb, ${color} ${active ? 25 : 10}%, transparent)` }}
        aria-label={label}
      >
        {id}
      </button>
      {hover && (
        <span role="tooltip" className="absolute bottom-full left-0 z-30 mb-1 block w-80 rounded-[8px] border border-line bg-elevated p-3 text-xs leading-relaxed text-primary shadow-xl">
          {state === "current" && ev && (
            <>
              <span className="mb-1 flex items-center justify-between gap-2 text-muted">
                <span className="num">{id}</span>
                <span className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[ev.severity] }} aria-hidden />
                  {ev.kind} · {ev.source}
                </span>
              </span>
              <span className="block">{ev.statement}</span>
            </>
          )}
          {state === "earlier" && (
            <span className="text-secondary">
              From an earlier run (<span className="num">{originRunId}</span>). This action was proposed then and keeps the evidence of that run; the current run cites its own evidence in the report.
            </span>
          )}
          {state === "unknown" && <span className="text-risk-critical">This id is not in the evidence ledger of any run shown here.</span>}
        </span>
      )}
    </span>
  );
}

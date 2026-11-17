/**
 * `EVD-` citation chip with a hover card showing the evidence statement. Click
 * jumps to the item in the evidence list. Unknown ids render as broken (red).
 */
import { useState } from "react";
import { SEVERITY_COLOR } from "../../lib/meta";
import { useEvidenceCtx } from "./EvidenceContext";

export function EvdChip({ id }: { id: string }) {
  const { byId, highlighted, jumpTo } = useEvidenceCtx();
  const [hover, setHover] = useState(false);
  const ev = byId.get(id);
  const active = highlighted === id;
  const color = ev ? "var(--c-accent)" : "var(--c-risk-critical)";
  return (
    <span className="relative inline-block align-baseline" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button
        type="button"
        onClick={() => jumpTo(id)}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        className="num mx-0.5 rounded border px-1 text-[11px] leading-4"
        style={{ color, borderColor: `color-mix(in srgb, ${color} ${active ? 90 : 40}%, transparent)`, background: `color-mix(in srgb, ${color} ${active ? 25 : 10}%, transparent)` }}
        aria-label={ev ? `Evidence ${id}: ${ev.statement}` : `Unknown evidence ${id}`}
      >
        {id}
      </button>
      {hover && (
        <span role="tooltip" className="absolute bottom-full left-0 z-30 mb-1 block w-80 rounded-[8px] border border-line bg-elevated p-3 text-xs leading-relaxed text-primary shadow-xl">
          {ev ? (
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
          ) : (
            <span className="text-risk-critical">This id is not in the evidence ledger of the current run.</span>
          )}
        </span>
      )}
    </span>
  );
}

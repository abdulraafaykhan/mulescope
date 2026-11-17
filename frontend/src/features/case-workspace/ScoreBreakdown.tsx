/**
 * Score breakdown: one bar per fired risk signal (positive) and mitigator
 * (negative), from the `signal` evidence written by score_and_policy, plus
 * typology chips. Clicking a bar highlights its evidence item.
 */
import type { Evidence } from "../../types/api";
import { Panel, Skeleton } from "../../components/ui/primitives";
import { Chip } from "../../components/ui/chips";
import { humanize } from "../../lib/format";
import { scoreColor } from "../../lib/meta";
import { useEvidenceCtx } from "./EvidenceContext";

const MAX_POINTS = 20;

export function ScoreBreakdown({ evidence, score, typologies, loading }: { evidence: Evidence[]; score: number | null; typologies: string[]; loading: boolean }) {
  const { highlighted, jumpTo } = useEvidenceCtx();
  const signals = evidence
    .filter((e) => e.kind === "signal")
    .map((e) => ({ id: e.id, name: String(e.data.name ?? e.key), kind: String(e.data.kind ?? "risk"), points: Number(e.data.points ?? 0) }))
    .sort((a, b) => (a.kind === b.kind ? b.points - a.points : a.kind === "risk" ? -1 : 1));
  const risk = signals.filter((s) => s.kind === "risk").reduce((t, s) => t + s.points, 0);
  const mit = signals.filter((s) => s.kind !== "risk").reduce((t, s) => t + s.points, 0);

  return (
    <Panel title="Score breakdown" actions={<span className="num text-sm font-semibold" style={{ color: scoreColor(score) }}>{score == null ? "—" : `${score.toFixed(0)} / 100`}</span>}>
      <div className="p-3">
        {loading && <Skeleton className="h-24 w-full" />}
        {!loading && signals.length === 0 && <p className="text-sm text-muted">Start an investigation to score this case.</p>}
        {signals.length > 0 && (
          <>
            <div className="mb-2 flex justify-between text-xs text-muted">
              <span>Risk <span className="num text-risk-critical">+{risk.toFixed(0)}</span></span>
              <span>Mitigators <span className="num text-risk-low">−{mit.toFixed(0)}</span></span>
            </div>
            <ul className="space-y-1">
              {signals.map((s) => {
                const isRisk = s.kind === "risk";
                const color = isRisk ? "var(--c-risk-critical)" : "var(--c-risk-low)";
                const width = `${Math.min(100, (s.points / MAX_POINTS) * 100) / 2}%`;
                return (
                  <li key={s.id}>
                    <button type="button" onClick={() => jumpTo(s.id)} className={`grid w-full grid-cols-[1fr_40px] items-center gap-2 rounded px-1 py-0.5 text-left text-xs hover:bg-elevated ${highlighted === s.id ? "bg-elevated" : ""}`} title={`${s.id}: ${humanize(s.name)}`}>
                      <span>
                        <span className="block truncate text-secondary">{humanize(s.name)}</span>
                        <span className="relative mt-0.5 block h-1.5 rounded bg-elevated">
                          <span className="absolute top-0 left-1/2 h-full w-px bg-line" aria-hidden />
                          <span className="absolute top-0 h-full rounded" style={{ background: color, width, left: isRisk ? "50%" : undefined, right: isRisk ? undefined : "50%" }} />
                        </span>
                      </span>
                      <span className="num text-right" style={{ color }}>{isRisk ? "+" : "−"}{s.points.toFixed(0)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {typologies.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1 border-t border-line pt-3">
            {typologies.map((t) => (
              <Chip key={t} color="var(--c-role-receiver)">{humanize(t)}</Chip>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

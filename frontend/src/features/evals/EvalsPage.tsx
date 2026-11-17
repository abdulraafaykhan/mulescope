/**
 * Evals page: run history, headline metrics, 3x3 confusion matrix and the
 * per-scenario pass/fail table. Results are written by `uv run evals` (the
 * only process that reads ground truth); this page only displays them.
 */
import { useMemo, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, FlaskConical, XCircle } from "lucide-react";
import { useEvalRun, useEvalRuns } from "../../lib/queries";
import type { Disposition, EvalMetrics, EvalResult } from "../../types/api";
import { Empty, ErrorState, Panel, SkeletonRows } from "../../components/ui/primitives";
import { Chip, DispositionChip } from "../../components/ui/chips";
import { DISPOSITION_LABEL, int, istDateTime, ms, pct } from "../../lib/format";
import { DISPOSITION_COLOR } from "../../lib/meta";

const DISPS: Disposition[] = ["close", "escalate", "str_draft"];

function Metric({ label, value, target, ok }: { label: string; value: string; target?: string; ok?: boolean }) {
  return (
    <div className="rounded-[8px] border border-line bg-panel px-3 py-2">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="num text-xl font-semibold" style={{ color: ok === undefined ? undefined : ok ? "var(--c-risk-low)" : "var(--c-risk-critical)" }}>{value}</div>
      {target && <div className="text-[11px] text-muted">target {target}</div>}
    </div>
  );
}

function Confusion({ m }: { m: EvalMetrics }) {
  return (
    <table className="num text-sm">
      <thead>
        <tr>
          <th className="px-2 py-1 text-left text-[11px] font-normal text-muted">expected ↓ / predicted →</th>
          {DISPS.map((d) => <th key={d} className="px-3 py-1 text-xs font-medium" style={{ color: DISPOSITION_COLOR[d] }}>{DISPOSITION_LABEL[d]}</th>)}
        </tr>
      </thead>
      <tbody>
        {DISPS.map((exp) => (
          <tr key={exp}>
            <th className="px-2 py-1 text-left text-xs font-medium" style={{ color: DISPOSITION_COLOR[exp] }}>{DISPOSITION_LABEL[exp]}</th>
            {DISPS.map((pred) => {
              const n = m.confusion[exp]?.[pred] ?? 0;
              const diag = exp === pred;
              return (
                <td key={pred} className="h-12 w-20 border border-line text-center text-base" style={{ background: n ? (diag ? "color-mix(in srgb, var(--c-risk-low) 18%, transparent)" : "color-mix(in srgb, var(--c-risk-critical) 18%, transparent)") : undefined, color: n ? undefined : "var(--c-text-muted)" }}>
                  {n}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function byFamily(results: EvalResult[]) {
  const fam = new Map<string, { family: string; pass: number; fail: number }>();
  for (const r of results) {
    const family = r.scenario_type.split(".")[0];
    const f = fam.get(family) ?? { family, pass: 0, fail: 0 };
    if (r.correct) f.pass += 1;
    else f.fail += 1;
    fam.set(family, f);
  }
  return [...fam.values()];
}

export default function EvalsPage() {
  const runs = useEvalRuns();
  const [selected, setSelected] = useState<string | null>(null);
  const runId = selected ?? runs.data?.[0]?.id ?? null;
  const detail = useEvalRun(runId);
  const results = useMemo(() => [...(detail.data?.results ?? [])].sort((a, b) => a.scenario_type.localeCompare(b.scenario_type)), [detail.data]);
  const m = detail.data?.run.metrics ?? null;

  return (
    <div className="mx-auto flex h-full max-w-[1600px] flex-col gap-3 overflow-y-auto p-4">
      <div className="flex items-center justify-between rounded-[8px] border border-risk-medium/40 bg-risk-medium/10 px-4 py-2 text-sm text-risk-medium">
        <span className="flex items-center gap-2"><FlaskConical size={16} aria-hidden /> Evals compare runs against planted ground truth. This is the only screen that shows it; the API and agents never read the truth database.</span>
        <span className="num text-xs">uv run evals --mode fallback|live</span>
      </div>
      {runs.isLoading && <SkeletonRows rows={6} />}
      {runs.isError && <ErrorState error={runs.error} />}
      {runs.data && runs.data.length === 0 && <Empty>No eval runs yet. Run `uv run evals --mode fallback` from the mulescope folder.</Empty>}
      {runs.data && runs.data.length > 0 && (
        <div className="grid min-h-0 grid-cols-[260px_minmax(0,1fr)] gap-3">
          <Panel title="Run history" bodyClass="max-h-[70vh] overflow-y-auto">
            <ul>
              {runs.data.map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => setSelected(r.id)} className={`block w-full border-b border-line/60 px-3 py-2 text-left hover:bg-elevated ${r.id === runId ? "bg-elevated" : ""}`}>
                    <span className="flex items-center justify-between">
                      <span className="num text-sm text-accent">{r.id}</span>
                      <Chip color={r.mode === "live" ? "var(--c-agent-flow)" : "var(--c-risk-medium)"}>{r.mode}</Chip>
                    </span>
                    <span className="num block text-[11px] text-muted">{istDateTime(r.started_at)} · {r.status}</span>
                    {r.metrics && <span className="num block text-xs text-secondary">accuracy {pct(r.metrics.accuracy)} · {r.metrics.evaluated}/{r.metrics.total}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <div className="flex min-w-0 flex-col gap-3">
            {detail.isLoading && <SkeletonRows rows={8} />}
            {m && detail.data && (
              <>
                <div className="grid grid-cols-3 gap-2 xl:grid-cols-6">
                  <Metric label="Disposition accuracy" value={`${pct(m.accuracy)} (${m.correct}/${m.evaluated})`} target="≥ 90%" ok={m.accuracy >= 0.9} />
                  <Metric label="Mules closed" value={int(m.mules_closed)} target="0" ok={m.mules_closed === 0} />
                  <Metric label="Citation validity" value={pct(m.citation_validity, 1)} target="100%" ok={m.citation_validity >= 1} />
                  <Metric label="Claim coverage" value={pct(m.claim_coverage, 1)} target="≥ 95%" ok={m.claim_coverage >= 0.95} />
                  <Metric label="Tipping-off violations" value={int(m.tipping_off_violations)} target="0" ok={m.tipping_off_violations === 0} />
                  <Metric label="Injection obeyed" value={int(m.injection_obeyed)} target="never" ok={m.injection_obeyed === 0} />
                  <Metric label="Fallback rate" value={pct(m.fallback_rate)} />
                  <Metric label="Latency p50" value={ms(m.latency_ms_p50)} />
                  <Metric label="Latency p95" value={ms(m.latency_ms_p95)} />
                  <Metric label="Tokens total" value={int(m.tokens_total)} />
                  <Metric label="Tokens per case" value={int(Math.round(m.tokens_per_case))} />
                  <Metric label="Policy / graph" value={`${detail.data.run.policy_version} / ${detail.data.run.graph_version}`} />
                </div>
                <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-3">
                  <Panel title="Confusion matrix" bodyClass="p-3"><Confusion m={m} /></Panel>
                  <Panel title="Pass / fail by scenario family" bodyClass="h-52 p-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={byFamily(results)} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                        <XAxis dataKey="family" tick={{ fill: "var(--c-text-muted)", fontSize: 11 }} stroke="var(--c-border)" />
                        <YAxis allowDecimals={false} tick={{ fill: "var(--c-text-muted)", fontSize: 11 }} stroke="var(--c-border)" width={28} />
                        <Tooltip contentStyle={{ background: "var(--c-bg-elevated)", border: "1px solid var(--c-border)", borderRadius: 8, fontSize: 12 }} />
                        <Bar dataKey="pass" stackId="a" name="pass" fill="var(--c-risk-low)" />
                        <Bar dataKey="fail" stackId="a" name="fail" fill="var(--c-risk-critical)" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Panel>
                </div>
              </>
            )}
            {detail.data && !m && <Panel bodyClass="p-3"><p className="text-sm text-muted">This run has not finished; partial results below.</p></Panel>}
            {results.length > 0 && (
              <Panel title={`Per-scenario results (${results.length})`} bodyClass="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-elevated text-left text-secondary">
                    <tr>{["", "Scenario", "Case", "Label", "Expected", "Predicted", "Score", "Citations", "Coverage", "Fallback nodes", "Latency", "Tokens"].map((h) => <th key={h} className="px-3 py-1.5 font-medium">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {results.map((r) => (
                      <tr key={r.id} className="border-b border-line/50">
                        <td className="px-3 py-1">{r.correct ? <CheckCircle2 size={14} className="text-risk-low" aria-label="pass" /> : <XCircle size={14} className="text-risk-critical" aria-label="fail" />}</td>
                        <td className="num px-3 py-1 text-primary">{r.scenario_type}</td>
                        <td className="num px-3 py-1 text-accent"><a href={`/cases/${r.case_id}`} className="hover:underline">{r.case_id}</a></td>
                        <td className="px-3 py-1 text-secondary">{r.label}</td>
                        <td className="px-3 py-1"><DispositionChip value={r.expected} /></td>
                        <td className="px-3 py-1"><DispositionChip value={r.predicted} /></td>
                        <td className="num px-3 py-1 text-right">{r.score ?? "—"}</td>
                        <td className="num px-3 py-1 text-right" style={{ color: r.invalid_citations ? "var(--c-risk-critical)" : undefined }}>{r.citations}{r.invalid_citations ? ` (${r.invalid_citations} bad)` : ""}</td>
                        <td className="num px-3 py-1 text-right">{pct(r.claim_coverage)}</td>
                        <td className="num px-3 py-1 text-right">{r.fallback_nodes}</td>
                        <td className="num px-3 py-1 text-right">{ms(r.latency_ms)}</td>
                        <td className="num px-3 py-1 text-right">{int(r.tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

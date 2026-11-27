/**
 * Observability page: estimated LLM cost, tokens, latency and failures of the
 * four agents, from the `llm_calls` log (one row per call attempt). Period and
 * the opened run live in the URL (`?period=7d&run=RUN-...`), so a run can be
 * linked from the case page. Refreshes every 15 s.
 */
import type { ReactNode } from "react";
import { useSearchParams } from "react-router";
import { Info } from "lucide-react";
import { useObservabilitySummary, useObservedRuns, usePublicConfig } from "../../lib/queries";
import type { AgentKind, AgentUsage, ObservabilityPeriod, ObservabilitySummary } from "../../types/api";
import { Empty, ErrorState, Panel, SkeletonRows } from "../../components/ui/primitives";
import { istDateTime } from "../../lib/format";
import { GRAPH_NODES } from "../../lib/meta";
import { SummaryTiles } from "./SummaryTiles";
import { LatencyByAgent, OutcomeBreakdown, UsageOverTime } from "./UsageCharts";
import { AgentUsageTable, FreeTierWatch, ModelUsageTable } from "./UsageTables";
import { RunsTable } from "./RunsTable";
import { RunDetailDrawer } from "./RunDetailDrawer";

const PERIODS: { id: ObservabilityPeriod; label: string }[] = [
  { id: "24h", label: "Last 24 h" },
  { id: "7d", label: "Last 7 days" },
  { id: "all", label: "All (30-day log)" },
];
const DEFAULT_PERIOD: ObservabilityPeriod = "7d";
const AGENT_ORDER: AgentKind[] = GRAPH_NODES.map((n) => n.agent).filter((a, i, all) => a !== "code" && all.indexOf(a) === i);
const NO_CALLS = "No LLM calls in this period. Agents call the LLM only in live mode (LLM_MODE=live); runs in fallback mode use templates and cost nothing.";

function isPeriod(value: string | null): value is ObservabilityPeriod {
  return PERIODS.some((p) => p.id === value);
}

function PeriodPicker({ value, onChange }: { value: ObservabilityPeriod; onChange: (p: ObservabilityPeriod) => void }) {
  return (
    <div className="flex rounded-md border border-line bg-elevated p-0.5" role="radiogroup" aria-label="Period">
      {PERIODS.map((p) => (
        <button key={p.id} type="button" role="radio" aria-checked={value === p.id} onClick={() => onChange(p.id)} className={`rounded px-3 py-1 text-sm ${value === p.id ? "bg-panel text-primary shadow" : "text-secondary hover:text-primary"}`}>
          {p.label}
        </button>
      ))}
    </div>
  );
}

function ChartPanel({ title, children, height = "h-64" }: { title: string; children: ReactNode; height?: string }) {
  return <Panel title={title} bodyClass={`${height} p-3`}>{children}</Panel>;
}

/** Agents in graph order (profiler, flow analyst, narrative, critic); unknown last. */
function inGraphOrder(agents: AgentUsage[]): AgentUsage[] {
  const rank = (a: AgentUsage) => (a.agent ? AGENT_ORDER.indexOf(a.agent) : AGENT_ORDER.length);
  return [...agents].sort((a, b) => rank(a) - rank(b));
}

function Dashboard({ s }: { s: ObservabilitySummary }) {
  const hasCalls = s.totals.attempts > 0;
  const agents = inGraphOrder(s.by_agent);
  return (
    <>
      <SummaryTiles t={s.totals} />
      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <ChartPanel title="Tokens and estimated cost over time">
          {hasCalls ? <UsageOverTime points={s.series.points} bucket={s.series.bucket} since={s.since} until={s.generated_at} /> : <Empty>{NO_CALLS}</Empty>}
        </ChartPanel>
        <Panel title="Free-tier watch · last minute" bodyClass="p-3"><FreeTierWatch limits={s.rate_limits} pricing={s.pricing} /></Panel>
      </div>
      {hasCalls && (
        <div className="grid gap-3 lg:grid-cols-3">
          <ChartPanel title="Latency by agent"><LatencyByAgent agents={agents} /></ChartPanel>
          <Panel title="By model" bodyClass="h-64 overflow-y-auto p-3"><ModelUsageTable models={s.by_model} /></Panel>
          <Panel title="Attempt outcomes" bodyClass="h-64 overflow-y-auto p-3"><OutcomeBreakdown outcomes={s.outcomes} /></Panel>
        </div>
      )}
      {hasCalls && <Panel title="Agents" bodyClass="overflow-x-auto"><AgentUsageTable agents={agents} /></Panel>}
    </>
  );
}

export default function ObservabilityPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("period");
  const period = isPeriod(raw) ? raw : DEFAULT_PERIOD;
  const runId = params.get("run");
  const summary = useObservabilitySummary(period);
  const runs = useObservedRuns(period);
  const config = usePublicConfig();

  const update = (key: string, value: string | null) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-3 p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Observability</h1>
            <p className="text-xs text-muted">Estimated LLM cost, tokens, latency and failures of the four agents, one record per call attempt.{summary.data && ` Updated ${istDateTime(summary.data.generated_at)}.`}</p>
          </div>
          <PeriodPicker value={period} onChange={(p) => update("period", p)} />
        </div>
        {config.data?.llm_mode === "fallback" && (
          <div role="status" className="flex items-center gap-2 rounded-[8px] border border-risk-medium/40 bg-risk-medium/10 px-4 py-2 text-sm text-risk-medium">
            <Info size={15} aria-hidden /> The API runs with LLM_MODE=fallback, so new runs make no LLM calls. Earlier live calls still show here.
          </div>
        )}
        {summary.isLoading && <SkeletonRows rows={8} />}
        {summary.isError && <ErrorState error={summary.error} />}
        {summary.data && <Dashboard s={summary.data} />}
        <Panel title={`Runs (${runs.data?.length ?? 0})`} bodyClass="max-h-[480px] overflow-auto">
          {runs.isLoading && <SkeletonRows rows={6} />}
          {runs.isError && <ErrorState error={runs.error} />}
          {runs.data && runs.data.length === 0 && <Empty>No runs started in this period.</Empty>}
          {runs.data && runs.data.length > 0 && <RunsTable runs={runs.data} selected={runId} onSelect={(id) => update("run", id)} />}
        </Panel>
      </div>
      <RunDetailDrawer runId={runId} onClose={() => update("run", null)} />
    </div>
  );
}

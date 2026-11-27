/**
 * Charts of the observability page: tokens and estimated cost over time
 * (buckets with no calls are filled with zero so the time axis is even),
 * latency by agent (average and p95), and the outcome breakdown of every
 * attempt. Pure presentation; the page passes the summary down.
 */
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AgentUsage, LlmCallOutcome, UsagePoint } from "../../types/api";
import { int, intCompact, istDay, istTime, ms, usd } from "../../lib/format";
import { AGENT_COLOR, AGENT_LABEL, OUTCOME_META } from "../../lib/meta";

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;
// IST is UTC+5:30 with no daylight saving, so buckets are fixed-length.
const IST_OFFSET_MS = 330 * 60_000;
const AXIS = { fill: "var(--c-text-muted)", fontSize: 11 };
const TOOLTIP = { background: "var(--c-bg-elevated)", border: "1px solid var(--c-border)", borderRadius: 8, fontSize: 12 };

function bucketStart(ts: number, size: number): number {
  return Math.floor((ts + IST_OFFSET_MS) / size) * size - IST_OFFSET_MS;
}

/** Every bucket from `since` to `until`, zero where the API returned none. */
function fillSeries(points: UsagePoint[], bucket: "hour" | "day", since: string, until: string) {
  const size = bucket === "hour" ? HOUR_MS : DAY_MS;
  const byStart = new Map(points.map((p) => [new Date(p.ts).getTime(), p]));
  const out = [];
  for (let t = bucketStart(new Date(since).getTime(), size); t <= new Date(until).getTime(); t += size) {
    const p = byStart.get(t);
    const iso = new Date(t).toISOString();
    out.push({ label: bucket === "hour" ? istTime(iso).slice(0, 5) : istDay(iso), tokens_in: p?.tokens_in ?? 0, tokens_out: p?.tokens_out ?? 0, cost_usd: p?.cost_usd ?? 0, attempts: p?.attempts ?? 0 });
  }
  return out;
}

export function UsageOverTime({ points, bucket, since, until }: { points: UsagePoint[]; bucket: "hour" | "day"; since: string; until: string }) {
  const data = useMemo(() => fillSeries(points, bucket, since, until), [points, bucket, since, until]);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
        <CartesianGrid stroke="var(--c-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={AXIS} stroke="var(--c-border)" minTickGap={16} />
        <YAxis yAxisId="tok" tickFormatter={intCompact} tick={AXIS} stroke="var(--c-border)" width={44} />
        <YAxis yAxisId="usd" orientation="right" tickFormatter={(v: number) => usd(v)} tick={AXIS} stroke="var(--c-border)" width={64} />
        <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: "var(--c-text-primary)" }} formatter={(v, name) => [name === "Est. cost" ? usd(Number(v)) : int(Number(v)), String(name)]} />
        <Legend wrapperStyle={{ fontSize: 12, color: "var(--c-text-secondary)" }} />
        <Bar yAxisId="tok" dataKey="tokens_in" name="Tokens in" stackId="t" fill="var(--c-role-sender)" />
        <Bar yAxisId="tok" dataKey="tokens_out" name="Tokens out" stackId="t" fill="var(--c-role-receiver)" radius={[2, 2, 0, 0]} />
        {/* Straight segments: a smoothed curve would overshoot between buckets and invent cost. */}
        <Line yAxisId="usd" dataKey="cost_usd" name="Est. cost" stroke="var(--c-risk-medium)" strokeWidth={2} dot={false} type="linear" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function LatencyByAgent({ agents }: { agents: AgentUsage[] }) {
  const data = agents.map((a) => ({ name: a.agent ? AGENT_LABEL[a.agent] : "Outside a step", agent: a.agent, avg: a.avg_latency_ms ?? 0, p95: a.p95_latency_ms ?? 0 }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
        <CartesianGrid stroke="var(--c-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" tick={AXIS} stroke="var(--c-border)" interval={0} />
        <YAxis tickFormatter={(v: number) => ms(v)} tick={AXIS} stroke="var(--c-border)" width={56} />
        <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: "var(--c-text-primary)" }} formatter={(v, name) => [ms(Number(v)), String(name)]} cursor={{ fill: "var(--c-bg-elevated)" }} />
        {/* A swatch cannot show four agent colours, so the legend says it in words. */}
        <Legend content={() => <p className="text-center text-xs text-secondary">Left bar: average, in the agent's colour · grey bar: p95 (95% of attempts were faster)</p>} />
        <Bar dataKey="avg" name="Average" radius={[2, 2, 0, 0]}>
          {data.map((d) => <Cell key={d.name} fill={d.agent ? AGENT_COLOR[d.agent] : "var(--c-agent-code)"} />)}
        </Bar>
        <Bar dataKey="p95" name="p95" fill="var(--c-text-muted)" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function OutcomeBreakdown({ outcomes }: { outcomes: { outcome: LlmCallOutcome; count: number }[] }) {
  const total = outcomes.reduce((s, o) => s + o.count, 0);
  return (
    <ul className="space-y-2">
      {outcomes.map((o) => {
        const meta = OUTCOME_META[o.outcome];
        const share = total ? o.count / total : 0;
        return (
          <li key={o.outcome} className="text-xs">
            <div className="mb-0.5 flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-secondary"><span className="h-2 w-2 rounded-full" style={{ background: meta.color }} aria-hidden />{meta.label}</span>
              <span className="num text-primary">{int(o.count)} <span className="text-muted">({(share * 100).toFixed(0)}%)</span></span>
            </div>
            <div className="h-1.5 rounded bg-elevated"><div className="h-full rounded" style={{ width: `${share * 100}%`, background: meta.color }} /></div>
          </li>
        );
      })}
    </ul>
  );
}

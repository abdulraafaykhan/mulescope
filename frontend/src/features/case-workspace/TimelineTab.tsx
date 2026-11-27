/**
 * Timeline tab: daily inflow/outflow bars with the end-of-day balance line and
 * median exit-lag markers (minutes from a credit to the next debit). The brush
 * filters the event list below the chart.
 */
import { useMemo, useState } from "react";
import { Bar, Brush, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { useTimeline } from "../../lib/queries";
import type { TimelineEvent } from "../../types/api";
import { ErrorState, SkeletonRows } from "../../components/ui/primitives";
import { inr, inrCompact, istDateTime, minutes } from "../../lib/format";

const IST_OFFSET_MS = 330 * 60_000;

function istDayKey(iso: string): string {
  return new Date(new Date(iso).getTime() + IST_OFFSET_MS).toISOString().slice(0, 10);
}

/** Per IST day: median minutes from each credit to the next debit. */
function exitLags(events: TimelineEvent[]): Map<string, number> {
  const byDay = new Map<string, number[]>();
  events.forEach((e, i) => {
    if (e.direction !== "credit") return;
    const next = events.slice(i + 1).find((x) => x.direction === "debit");
    if (!next) return;
    const lag = (new Date(next.ts).getTime() - new Date(e.ts).getTime()) / 60_000;
    const key = istDayKey(e.ts);
    byDay.set(key, [...(byDay.get(key) ?? []), lag]);
  });
  const out = new Map<string, number>();
  byDay.forEach((lags, key) => {
    const s = [...lags].sort((a, b) => a - b);
    out.set(key, s[Math.floor(s.length / 2)]);
  });
  return out;
}

const tooltipStyle = { background: "var(--c-bg-elevated)", border: "1px solid var(--c-border)", borderRadius: 8, fontSize: 12 };

export function TimelineTab({ caseId }: { caseId: string }) {
  const timeline = useTimeline(caseId);
  const [range, setRange] = useState<[number, number] | null>(null);

  const data = useMemo(() => {
    if (!timeline.data) return [];
    const lags = exitLags(timeline.data.events);
    return timeline.data.days.map((d) => ({ ...d, label: d.date.slice(5), lag: lags.get(d.date) ?? null }));
  }, [timeline.data]);

  const events = useMemo(() => {
    if (!timeline.data) return [];
    const [a, b] = range ?? [0, data.length - 1];
    const from = data[a]?.date ?? "";
    const to = data[b]?.date ?? "9999";
    return timeline.data.events.filter((e) => {
      const k = istDayKey(e.ts);
      return k >= from && k <= to;
    });
  }, [timeline.data, data, range]);

  if (timeline.isLoading) return <SkeletonRows rows={8} />;
  if (timeline.isError) return <ErrorState error={timeline.error} />;

  return (
    // Chart and entry list share the height (3:2) so neither spills out of the panel.
    <div className="flex h-full flex-col overflow-hidden">
      <div className="min-h-[200px] flex-3 px-3 pt-3 pb-1">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="var(--c-border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: "var(--c-text-muted)", fontSize: 11 }} stroke="var(--c-border)" />
            <YAxis yAxisId="amt" tickFormatter={inrCompact} tick={{ fill: "var(--c-text-muted)", fontSize: 11 }} stroke="var(--c-border)" width={56} />
            <YAxis
              yAxisId="lag"
              orientation="right"
              tickFormatter={(v: number) => minutes(v)}
              tick={{ fill: "var(--c-text-muted)", fontSize: 11 }}
              stroke="var(--c-border)"
              width={52}
              label={{ value: "exit lag", angle: 90, position: "insideRight", fill: "var(--c-text-muted)", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={{ color: "var(--c-text-primary)" }}
              formatter={(value, name) => [name === "Exit lag" ? minutes(Number(value)) : inr(Number(value)), String(name)]}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "var(--c-text-secondary)" }} />
            <Bar yAxisId="amt" dataKey="inflow" name="Inflow" fill="var(--c-role-sender)" radius={[2, 2, 0, 0]} />
            <Bar yAxisId="amt" dataKey="outflow" name="Outflow" fill="var(--c-role-receiver)" radius={[2, 2, 0, 0]} />
            <Line yAxisId="amt" dataKey="balance" name="Balance" stroke="var(--c-risk-medium)" dot={false} strokeWidth={2} type="stepAfter" />
            <Scatter yAxisId="lag" dataKey="lag" name="Exit lag" fill="var(--c-risk-critical)" shape="diamond" />
            <Brush
              dataKey="label"
              height={16}
              stroke="var(--c-accent)"
              fill="var(--c-bg-elevated)"
              travellerWidth={8}
              onChange={(r) => {
                if (r.startIndex !== undefined && r.endIndex !== undefined) setRange([r.startIndex, r.endIndex]);
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="min-h-[96px] flex-2 overflow-y-auto border-t border-line">
        <div className="sticky top-0 bg-elevated px-3 py-1.5 text-xs text-secondary">{events.length} entries in the selected range · drag the bar under the chart to narrow it</div>
        <ul className="text-xs">
          {events.map((e, i) => (
            <li key={`${e.ts}-${i}`} className="grid grid-cols-[minmax(110px,150px)_16px_minmax(0,1fr)_minmax(90px,120px)_minmax(90px,120px)] items-center gap-2 border-b border-line/50 px-3 py-1">
              <span className="num text-muted">{istDateTime(e.ts)}</span>
              {e.direction === "credit" ? <ArrowDownLeft size={12} className="text-role-sender" aria-label="credit" /> : <ArrowUpRight size={12} className="text-role-receiver" aria-label="debit" />}
              <span className="num text-secondary uppercase">{e.channel.replace("_", " ")}</span>
              <span className="num text-right" style={{ color: e.direction === "credit" ? "var(--c-role-sender)" : "var(--c-role-receiver)" }}>{e.direction === "credit" ? "+" : "−"}{inr(e.amount)}</span>
              <span className="num text-right text-muted">{inr(e.balance)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

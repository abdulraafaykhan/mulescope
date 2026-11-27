/**
 * Headline tiles of the observability page: estimated cost (with what the
 * cache saved), tokens, requests and attempts, latency, and the four rates
 * (provider errors, template fallbacks, retries, cache hits). A rate whose
 * denominator is zero shows a dash, not 0%.
 */
import type { ReactNode } from "react";
import type { ObservabilityTotals } from "../../types/api";
import { int, ms, pct, usd } from "../../lib/format";

function Tile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: string }) {
  return (
    <div className="min-w-0 rounded-[8px] border border-line bg-panel px-3 py-2.5">
      <div className="truncate text-[11px] text-muted uppercase">{label}</div>
      <div className="num mt-0.5 truncate text-xl font-semibold" style={{ color: tone }}>{value}</div>
      {hint && <div className="num truncate text-[11px] text-muted">{hint}</div>}
    </div>
  );
}

/** Red above `bad`, amber above zero, green at zero. */
function rateTone(rate: number | null, bad: number): string | undefined {
  if (rate == null) return undefined;
  if (rate >= bad) return "var(--c-risk-critical)";
  return rate > 0 ? "var(--c-risk-medium)" : "var(--c-risk-low)";
}

const ERROR_BAD = 0.1;
const FALLBACK_BAD = 0.05;

export function SummaryTiles({ t }: { t: ObservabilityTotals }) {
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 2xl:grid-cols-8">
      <Tile label="Estimated cost" value={usd(t.cost_usd)} hint={t.saved_cost_usd ? `cache saved ${usd(t.saved_cost_usd)}` : "at Groq list price"} />
      <Tile label="Tokens in / out" value={`${int(t.tokens_in)} / ${int(t.tokens_out)}`} hint={t.saved_tokens_in + t.saved_tokens_out ? `${int(t.saved_tokens_in + t.saved_tokens_out)} served from cache` : undefined} />
      <Tile label="Requests" value={int(t.requests)} hint={`${int(t.attempts)} attempts · ${int(t.cache_hits)} cache hits`} />
      <Tile label="Latency avg / p95" value={`${ms(t.avg_latency_ms)}`} hint={`p95 ${ms(t.p95_latency_ms)}`} />
      <Tile label="Error rate" value={pct(t.error_rate, 1)} hint={`${int(t.errors)} of ${int(t.provider_attempts)} provider calls`} tone={rateTone(t.error_rate, ERROR_BAD)} />
      <Tile label="Fallback rate" value={pct(t.fallback_rate, 1)} hint={`${int(t.failed_requests)} of ${int(t.requests)} requests used the template`} tone={rateTone(t.fallback_rate, FALLBACK_BAD)} />
      <Tile label="Retry rate" value={pct(t.retry_rate, 1)} hint="requests needing more than one attempt" />
      <Tile label="Cache hit rate" value={pct(t.cache_hit_rate, 1)} hint={`${int(t.cache_hits)} of ${int(t.requests)} requests`} />
    </div>
  );
}

/**
 * Tables of the observability page: usage per agent (models, prompt versions,
 * requests, template fallbacks, tokens, latency, cost), usage per model, and
 * the free-tier watch (tokens in the last minute against each model's limit)
 * with the list prices the estimates use.
 */
import type { AgentUsage, ModelPrice, ModelUsage, RateLimitUsage } from "../../types/api";
import { int, ms, pct, usd } from "../../lib/format";
import { AGENT_COLOR, AGENT_LABEL } from "../../lib/meta";

const TH = "px-3 py-1.5 font-medium whitespace-nowrap";
const TD = "px-3 py-1.5";
// Above these shares of the per-minute limit the bar turns amber, then red.
const WATCH_WARN = 0.6;
const WATCH_BAD = 0.85;

export function AgentUsageTable({ agents }: { agents: AgentUsage[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="bg-elevated text-left text-secondary">
        <tr>
          <th className={TH}>Agent</th><th className={TH}>Model</th><th className={TH}>Prompt</th>
          <th className={`${TH} text-right`}>Requests</th><th className={`${TH} text-right`}>Fallbacks</th><th className={`${TH} text-right`}>Attempts</th>
          <th className={`${TH} text-right`}>Tokens in / out</th><th className={`${TH} text-right`}>Avg / p95</th><th className={`${TH} text-right`}>Est. cost</th>
        </tr>
      </thead>
      <tbody>
        {agents.map((a) => (
          <tr key={a.agent ?? "none"} className="border-b border-line/50 align-top">
            <td className={`${TD} font-medium`} style={{ color: a.agent ? AGENT_COLOR[a.agent] : undefined }}>{a.agent ? AGENT_LABEL[a.agent] : "Outside a step"}</td>
            <td className={`${TD} num text-secondary`}>{a.models.join(", ")}</td>
            <td className={`${TD} num text-muted`}>{a.prompt_versions.join(", ")}</td>
            <td className={`${TD} num text-right`}>{int(a.requests)}</td>
            <td className={`${TD} num text-right`} style={{ color: a.fallbacks ? "var(--c-risk-medium)" : undefined }}>{int(a.fallbacks)} <span className="text-muted">({pct(a.requests ? a.fallbacks / a.requests : null)})</span></td>
            <td className={`${TD} num text-right`}>{int(a.attempts)}{a.errors > 0 && <span className="text-risk-critical"> · {a.errors} failed</span>}</td>
            <td className={`${TD} num text-right`}>{int(a.tokens_in)} / {int(a.tokens_out)}</td>
            <td className={`${TD} num text-right`}>{ms(a.avg_latency_ms)} / {ms(a.p95_latency_ms)}</td>
            <td className={`${TD} num text-right text-primary`}>{usd(a.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ModelUsageTable({ models }: { models: ModelUsage[] }) {
  const total = models.reduce((s, m) => s + m.cost_usd, 0);
  return (
    <table className="w-full text-xs">
      <thead className="text-left text-muted">
        <tr><th className="py-1 pr-2 font-normal">Model</th><th className="py-1 pr-2 text-right font-normal">Attempts</th><th className="py-1 pr-2 text-right font-normal">Tokens</th><th className="py-1 pr-2 text-right font-normal">p95</th><th className="py-1 text-right font-normal">Est. cost</th></tr>
      </thead>
      <tbody>
        {models.map((m) => (
          <tr key={m.model} className="border-t border-line/50">
            <td className="num py-1.5 pr-2 break-all text-primary">{m.model}</td>
            <td className="num py-1.5 pr-2 text-right">{int(m.attempts)}</td>
            <td className="num py-1.5 pr-2 text-right">{int(m.tokens_in + m.tokens_out)}</td>
            <td className="num py-1.5 pr-2 text-right">{ms(m.p95_latency_ms)}</td>
            <td className="num py-1.5 text-right text-primary">{usd(m.cost_usd)}{total > 0 && <span className="block text-[11px] text-muted">{pct(m.cost_usd / total)}</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function watchColor(ratio: number): string {
  if (ratio >= WATCH_BAD) return "var(--c-risk-critical)";
  return ratio >= WATCH_WARN ? "var(--c-risk-medium)" : "var(--c-risk-low)";
}

export function FreeTierWatch({ limits, pricing }: { limits: RateLimitUsage[]; pricing: ModelPrice[] }) {
  return (
    <div className="space-y-4">
      <ul className="space-y-3">
        {limits.map((l) => (
          <li key={l.model} className="text-xs">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="num truncate text-secondary">{l.model}</span>
              <span className="num shrink-0 text-primary">{int(l.tokens_last_minute)} / {int(l.tokens_per_minute)} <span className="text-muted">tokens/min</span></span>
            </div>
            <div className="h-2 rounded bg-elevated" role="meter" aria-valuenow={l.tokens_last_minute} aria-valuemin={0} aria-valuemax={l.tokens_per_minute} aria-label={`${l.model} tokens in the last minute`}>
              <div className="h-full rounded transition-[width]" style={{ width: `${Math.min(1, l.usage_ratio) * 100}%`, background: watchColor(l.usage_ratio) }} />
            </div>
          </li>
        ))}
        {limits.length === 0 && <li className="text-xs text-muted">No per-minute limits configured.</li>}
      </ul>
      <div>
        <div className="mb-1 text-[11px] text-muted uppercase">Price basis (USD per million tokens)</div>
        <table className="w-full text-xs">
          <tbody>
            {pricing.map((p) => (
              <tr key={p.model} className="border-t border-line/50">
                <td className="num py-1 pr-2 break-all text-secondary">{p.model}</td>
                <td className="num py-1 pr-2 text-right">in {usd(p.input_usd_per_million)}</td>
                <td className="num py-1 text-right">out {usd(p.output_usd_per_million)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-[11px] text-muted">Groq list prices from config/llm.yaml. The free tier bills $0; these are estimates of what the calls would cost on a paid plan.</p>
      </div>
    </div>
  );
}

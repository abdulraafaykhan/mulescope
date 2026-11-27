/**
 * Runs started in the period, newest first, with their LLM usage (requests,
 * attempts, failed attempts, tokens, estimated cost, provider time). Runs in
 * fallback mode are listed too, with no calls. Row click (or Enter) opens the
 * run detail.
 */
import type { ObservedRun } from "../../types/api";
import { Chip } from "../../components/ui/chips";
import { humanize, int, istDateTime, ms, usd } from "../../lib/format";

const TH = "px-3 py-1.5 font-medium whitespace-nowrap";
const TD = "px-3 py-1.5";

export function RunsTable({ runs, selected, onSelect }: { runs: ObservedRun[]; selected: string | null; onSelect: (runId: string) => void }) {
  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 z-10 bg-elevated text-left text-secondary">
        <tr>
          <th className={TH}>Run</th><th className={TH}>Case</th><th className={TH}>Started</th><th className={TH}>Status</th><th className={TH}>Mode</th>
          <th className={`${TH} text-right`}>Requests</th><th className={`${TH} text-right`}>Attempts</th><th className={`${TH} text-right`}>Tokens</th>
          <th className={`${TH} text-right`}>LLM time</th><th className={`${TH} text-right`}>Est. cost</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr
            key={r.id}
            tabIndex={0}
            onClick={() => onSelect(r.id)}
            onKeyDown={(e) => e.key === "Enter" && onSelect(r.id)}
            aria-selected={selected === r.id}
            className={`cursor-pointer border-b border-line/50 hover:bg-elevated/70 focus:bg-elevated ${selected === r.id ? "bg-elevated" : ""}`}
          >
            <td className={`${TD} num text-accent`}>{r.id}</td>
            <td className={`${TD} num text-secondary`}>{r.case_id}</td>
            <td className={`${TD} num whitespace-nowrap text-muted`}>{istDateTime(r.started_at)}</td>
            <td className={TD}>{humanize(r.status)}</td>
            <td className={TD}><Chip color={r.llm_mode === "live" ? "var(--c-agent-flow)" : "var(--c-risk-medium)"}>{r.llm_mode}</Chip></td>
            <td className={`${TD} num text-right`}>{int(r.llm.requests)}</td>
            <td className={`${TD} num text-right`}>{int(r.llm.attempts)}{r.llm.errors > 0 && <span className="text-risk-critical"> · {r.llm.errors} failed</span>}</td>
            <td className={`${TD} num text-right`}>{int(r.llm.tokens_in + r.llm.tokens_out)}</td>
            <td className={`${TD} num text-right`}>{r.llm.attempts ? ms(r.llm.llm_latency_ms) : "—"}</td>
            <td className={`${TD} num text-right text-primary`}>{r.llm.attempts ? usd(r.llm.cost_usd) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Detail of one run in a side drawer: usage facts, every graph step with its
 * latency, model, tokens and estimated cost, and every LLM call attempt with
 * its outcome and error text. Opened from the runs table or a link with
 * `?run=RUN-...` (the case page's Diagnostics tab links here).
 */
import type { ReactNode } from "react";
import { Link } from "react-router";
import { useObservedRun } from "../../lib/queries";
import type { LlmAttemptRecord, ObservedStep, RunObservability } from "../../types/api";
import { Drawer } from "../../components/ui/overlays";
import { Chip } from "../../components/ui/chips";
import { ErrorState, SkeletonRows } from "../../components/ui/primitives";
import { humanize, int, istDateTime, istTime, ms, usd } from "../../lib/format";
import { AGENT_COLOR, AGENT_LABEL, GRAPH_NODES, NODE_STATUS_COLOR, OUTCOME_META } from "../../lib/meta";

const DRAWER_WIDTH = 920;
const NODE_LABEL = new Map(GRAPH_NODES.map((n) => [n.node, n.label]));
const TH = "px-2 py-1.5 font-medium whitespace-nowrap";
const TD = "px-2 py-1.5";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-elevated/40 px-3 py-2">
      <div className="text-[11px] text-muted uppercase">{label}</div>
      <div className="num truncate text-sm text-primary">{children}</div>
    </div>
  );
}

function Steps({ steps }: { steps: ObservedStep[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="bg-elevated text-left text-secondary">
        <tr><th className={TH}>Step</th><th className={TH}>Status</th><th className={`${TH} text-right`}>Latency</th><th className={TH}>Model</th><th className={`${TH} text-right`}>Tokens</th><th className={`${TH} text-right`}>Est. cost</th></tr>
      </thead>
      <tbody>
        {steps.map((s) => (
          <tr key={s.id} className="border-b border-line/50 align-top" title={s.fallback_reason ?? s.error ?? s.output_summary ?? undefined}>
            <td className={TD}><span style={{ color: AGENT_COLOR[s.agent] }}>{NODE_LABEL.get(s.node) ?? s.node}</span>{s.output_summary && <span className="block max-w-[260px] truncate text-muted">{s.output_summary}</span>}</td>
            <td className={TD}><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full" style={{ background: NODE_STATUS_COLOR[s.status] }} aria-hidden />{s.status}{s.cache_hit && <span className="text-muted">· cache</span>}</span></td>
            <td className={`${TD} num text-right`}>{ms(s.latency_ms)}</td>
            <td className={`${TD} num text-secondary`}>{s.agent === "code" ? "—" : s.model ?? "—"}</td>
            <td className={`${TD} num text-right`}>{s.tokens_in + s.tokens_out ? int(s.tokens_in + s.tokens_out) : "—"}</td>
            <td className={`${TD} num text-right`}>{s.cost_usd == null ? "—" : usd(s.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Attempts({ attempts }: { attempts: LlmAttemptRecord[] }) {
  if (!attempts.length) return <p className="text-xs text-muted">No LLM calls in this run. Runs in fallback mode use the template agents.</p>;
  return (
    <table className="w-full text-xs">
      <thead className="bg-elevated text-left text-secondary">
        <tr><th className={TH}>Time</th><th className={TH}>Step</th><th className={`${TH} text-right`}>#</th><th className={TH}>Model</th><th className={TH}>Outcome</th><th className={`${TH} text-right`}>Latency</th><th className={`${TH} text-right`}>In / out</th><th className={`${TH} text-right`}>Est. cost</th></tr>
      </thead>
      <tbody>
        {attempts.map((a) => {
          const meta = OUTCOME_META[a.outcome];
          return (
            <tr key={a.id} className="border-b border-line/50 align-top">
              <td className={`${TD} num text-muted`}>{istTime(a.created_at)}</td>
              <td className={TD} style={{ color: a.agent ? AGENT_COLOR[a.agent] : undefined }}>{a.agent ? AGENT_LABEL[a.agent] : a.node ?? "—"}</td>
              <td className={`${TD} num text-right text-muted`}>{a.attempt}</td>
              <td className={`${TD} num text-secondary`}>{a.model}<span className="block text-muted">{a.prompt_version}</span></td>
              <td className={TD}>
                <Chip color={meta.color}>{meta.label}</Chip>
                {a.error && <span className="num mt-1 block max-w-[320px] text-[11px] break-words text-risk-critical/90">{a.error}</span>}
              </td>
              <td className={`${TD} num text-right`}>{ms(a.latency_ms)}</td>
              <td className={`${TD} num text-right`}>{a.outcome === "cache_hit" ? <span className="text-muted">saved {int(a.saved_tokens_in + a.saved_tokens_out)}</span> : `${int(a.tokens_in)} / ${int(a.tokens_out)}`}</td>
              <td className={`${TD} num text-right`}>{usd(a.cost_usd)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Body({ data }: { data: RunObservability }) {
  const { run, steps, attempts } = data;
  const u = run.llm;
  return (
    <div className="space-y-5 p-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Fact label="Case"><Link to={`/cases/${run.case_id}`} className="text-accent hover:underline">{run.case_id}</Link></Fact>
        <Fact label="Status">{humanize(run.status)} · {run.llm_mode}</Fact>
        <Fact label="Started">{istDateTime(run.started_at)}</Fact>
        <Fact label="Ended">{istDateTime(run.ended_at)}</Fact>
        <Fact label="Estimated cost">{usd(u.cost_usd)}{u.saved_cost_usd > 0 && <span className="text-muted"> · saved {usd(u.saved_cost_usd)}</span>}</Fact>
        <Fact label="Tokens in / out">{int(u.tokens_in)} / {int(u.tokens_out)}</Fact>
        <Fact label="Requests · attempts">{int(u.requests)} · {int(u.attempts)}{u.errors > 0 && <span className="text-risk-critical"> · {u.errors} failed</span>}</Fact>
        <Fact label="LLM time">{ms(u.llm_latency_ms)}</Fact>
      </div>
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-secondary uppercase">Steps ({steps.length})</h3>
        <Steps steps={steps} />
      </section>
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-secondary uppercase">LLM call attempts ({attempts.length})</h3>
        <Attempts attempts={attempts} />
      </section>
    </div>
  );
}

export function RunDetailDrawer({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const run = useObservedRun(runId, false);
  return (
    <Drawer open={Boolean(runId)} onClose={onClose} title={<span className="num">{runId}</span>} width={DRAWER_WIDTH}>
      {run.isLoading && <SkeletonRows rows={10} />}
      {run.isError && <ErrorState error={run.error} />}
      {run.data && <Body data={run.data} />}
    </Drawer>
  );
}

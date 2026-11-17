/**
 * Report tab (section 9.5): executive summary through recommended actions (the
 * stored summary), STR narrative when the disposition is STR draft, the
 * neutral customer clarification for escalations, critic result and an
 * appendix with run metadata. Citations render as EVD chips. Exports Markdown
 * and prints with the print stylesheet.
 */
import { Download, Printer, ShieldAlert, ShieldCheck } from "lucide-react";
import type { CaseDetail, Report } from "../../types/api";
import { Button, Empty, Fact, SkeletonRows } from "../../components/ui/primitives";
import { Chip } from "../../components/ui/chips";
import { istDateTime } from "../../lib/format";
import { Markdown } from "./Markdown";

function exportMarkdown(report: Report, detail: CaseDetail) {
  const parts = [`# ${detail.case.id} report v${report.version}`, report.summary_md];
  if (report.str_narrative_md) parts.push(report.str_narrative_md);
  if (report.customer_query_md) parts.push("## Customer clarification draft", report.customer_query_md);
  const blob = new Blob([parts.join("\n\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${detail.case.id}-report-v${report.version}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportTab({ report, loading, detail }: { report: Report | null; loading: boolean; detail: CaseDetail }) {
  if (loading) return <SkeletonRows rows={10} />;
  if (!report) return <Empty>No report yet. Start an investigation; the narrative writer drafts it after scoring.</Empty>;
  const run = detail.run;
  const critic = report.critic;
  return (
    <div className="print-area h-full overflow-y-auto">
      <div className="no-print sticky top-0 z-10 flex items-center justify-between border-b border-line bg-panel px-4 py-2">
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="num">{report.id} · v{report.version}</span>
          <span>{report.status}</span>
          {critic && (
            <Chip color={critic.verdict === "pass" ? "var(--c-risk-low)" : "var(--c-risk-medium)"} icon={critic.verdict === "pass" ? <ShieldCheck size={12} aria-hidden /> : <ShieldAlert size={12} aria-hidden />}>
              Critic {critic.verdict}
            </Chip>
          )}
          <span>{report.citations.length} citations</span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => exportMarkdown(report, detail)}><Download size={12} aria-hidden /> Markdown</Button>
          <Button size="sm" onClick={() => window.print()}><Printer size={12} aria-hidden /> Print / PDF</Button>
        </div>
      </div>
      <article className="mx-auto max-w-[860px] px-6 py-4">
        {critic && critic.issues.length > 0 && (
          <div className="mb-3 rounded-md border border-risk-medium/40 bg-risk-medium/10 p-3 text-xs text-risk-medium">
            <div className="mb-1 font-semibold">Critic issues</div>
            <ul className="list-disc pl-4">{critic.issues.map((i) => <li key={i}>{i}</li>)}</ul>
          </div>
        )}
        <Markdown text={report.summary_md} />
        {report.str_narrative_md && (
          <div className="mt-4 rounded-[8px] border border-risk-critical/40 p-4">
            <Markdown text={report.str_narrative_md} />
          </div>
        )}
        {report.customer_query_md && (
          <div className="mt-4">
            <h2 className="mb-2 text-lg font-semibold">Customer clarification draft</h2>
            <p className="mb-2 text-xs text-muted">Neutral wording: checked by the critic for tipping-off terms.</p>
            <pre className="rounded-[8px] border border-line bg-elevated p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap text-secondary">{report.customer_query_md}</pre>
          </div>
        )}
        <section className="mt-6 border-t border-line pt-4">
          <h2 className="mb-2 text-lg font-semibold">Appendix</h2>
          {run ? (
            <div className="grid grid-cols-2 gap-x-8">
              <Fact label="Run" mono>{run.id}</Fact>
              <Fact label="LLM mode">{run.llm_mode}</Fact>
              <Fact label="Graph version" mono>{run.graph_version}</Fact>
              <Fact label="Dataset seed" mono>{run.dataset_seed ?? "—"}</Fact>
              <Fact label="Started">{istDateTime(run.started_at)}</Fact>
              <Fact label="Ended">{istDateTime(run.ended_at)}</Fact>
              {Object.entries(run.models).map(([agent, model]) => <Fact key={agent} label={`Model · ${agent}`} mono>{model}</Fact>)}
              {Object.entries(run.prompt_versions).map(([agent, v]) => <Fact key={agent} label={`Prompt · ${agent}`} mono>{v}</Fact>)}
            </div>
          ) : (
            <p className="text-sm text-muted">No run metadata.</p>
          )}
        </section>
      </article>
    </div>
  );
}

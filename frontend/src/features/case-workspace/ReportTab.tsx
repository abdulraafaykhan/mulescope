/**
 * Report tab (section 9.5), laid out as a document: a title block with the
 * case facts and the recommendation, critic issues, the stored summary
 * (executive summary through recommended actions), the STR narrative when the
 * disposition is STR draft, the neutral customer clarification for
 * escalations, and an appendix with run metadata. Citations render as EVD
 * chips. The toolbar scrolls with the document so the text gets the height.
 * Exports Markdown and prints with the print stylesheet.
 */
import type { ReactNode } from "react";
import { Download, Printer, ShieldAlert, ShieldCheck } from "lucide-react";
import type { CaseDetail, Report } from "../../types/api";
import { Button, Empty, Fact, SkeletonRows } from "../../components/ui/primitives";
import { Chip, DispositionChip } from "../../components/ui/chips";
import { humanize, istDate, istDateTime } from "../../lib/format";
import { scoreColor } from "../../lib/meta";
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

function TitleItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted uppercase">{label}</div>
      <div className="mt-0.5 truncate text-sm text-primary">{children}</div>
    </div>
  );
}

function TitleBlock({ report, detail }: { report: Report; detail: CaseDetail }) {
  const { case: c, account, alert } = detail;
  return (
    <header className="mb-5 rounded-[8px] border border-line bg-elevated/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold text-primary">Case report <span className="num text-secondary">{c.id}</span></h1>
        <span className="num text-xs text-muted">{report.id} · v{report.version} · {humanize(report.status)} · {istDateTime(report.created_at)}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
        <TitleItem label="Account holder">{account.holder_name} · <span className="num">{account.account_no_masked}</span></TitleItem>
        <TitleItem label="Alert window"><span className="num">{istDate(alert.window.start)} to {istDate(alert.window.end)}</span></TitleItem>
        <TitleItem label="Alert rule"><span className="num">{alert.rule_id}</span></TitleItem>
        <TitleItem label="Risk score"><span className="num font-semibold" style={{ color: scoreColor(c.score) }}>{c.score ?? "—"}</span> / 100</TitleItem>
        <TitleItem label="Recommended"><DispositionChip value={c.recommended_disposition} /></TitleItem>
        {c.final_disposition && <TitleItem label="Final (analyst)"><DispositionChip value={c.final_disposition} /></TitleItem>}
      </div>
    </header>
  );
}

function Toolbar({ report, detail }: { report: Report; detail: CaseDetail }) {
  const critic = report.critic;
  return (
    <div className="no-print flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
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
  );
}

function Appendix({ detail }: { detail: CaseDetail }) {
  const run = detail.run;
  return (
    <section className="mt-8 border-t border-line pt-4">
      <h2 className="mb-2 text-base font-semibold text-primary">Appendix: run metadata</h2>
      {run ? (
        <div className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
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
  );
}

export function ReportTab({ report, loading, detail }: { report: Report | null; loading: boolean; detail: CaseDetail }) {
  if (loading) return <SkeletonRows rows={10} />;
  if (!report) return <Empty>No report yet. Start an investigation; the narrative writer drafts it after scoring.</Empty>;
  const issues = report.critic?.issues ?? [];
  return (
    <div className="print-area h-full overflow-y-auto">
      <Toolbar report={report} detail={detail} />
      <article className="mx-auto max-w-[860px] px-6 py-5">
        <TitleBlock report={report} detail={detail} />
        {issues.length > 0 && (
          <div className="mb-4 rounded-md border border-risk-medium/40 bg-risk-medium/10 p-3 text-xs text-risk-medium">
            <div className="mb-1 font-semibold">Critic issues</div>
            <ul className="list-disc pl-4">{issues.map((i) => <li key={i}>{i}</li>)}</ul>
          </div>
        )}
        <Markdown text={report.summary_md} />
        {report.str_narrative_md && (
          <section className="mt-6 rounded-[8px] border border-risk-critical/40 p-4">
            <Markdown text={report.str_narrative_md} />
          </section>
        )}
        {report.customer_query_md && (
          <section className="mt-6">
            <h2 className="mb-1 text-base font-semibold text-primary">Customer clarification draft</h2>
            <p className="mb-2 text-xs text-muted">Neutral wording, checked by the critic for tipping-off terms.</p>
            <div className="rounded-[8px] border border-line bg-elevated/40 p-5 text-sm leading-relaxed whitespace-pre-wrap text-secondary">{report.customer_query_md}</div>
          </section>
        )}
        <Appendix detail={detail} />
      </article>
    </div>
  );
}

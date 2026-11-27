/**
 * Report editor used by the Edit decision: one tab per editable field (case
 * summary, STR narrative, customer letter, whichever the report has), the
 * text on the left and a live preview on the right, rendered exactly like the
 * Report tab. Warns when a citation the draft had is no longer in the text.
 */
import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import type { Report } from "../../types/api";
import { Markdown } from "./Markdown";

export type EditableField = "summary_md" | "str_narrative_md" | "customer_query_md";
export type ReportEdits = Partial<Record<EditableField, string>>;

const LABEL: Record<EditableField, string> = { summary_md: "Case summary", str_narrative_md: "STR narrative", customer_query_md: "Customer letter" };
const EVD = /EVD-\d{6}/g;

/** The fields this report has, with their current text. */
export function editableFields(report: Report): ReportEdits {
  const out: ReportEdits = { summary_md: report.summary_md };
  if (report.str_narrative_md != null) out.str_narrative_md = report.str_narrative_md;
  if (report.customer_query_md != null) out.customer_query_md = report.customer_query_md;
  return out;
}

function droppedCitations(original: string, edited: string): string[] {
  const kept = new Set(edited.match(EVD) ?? []);
  return [...new Set(original.match(EVD) ?? [])].filter((id) => !kept.has(id));
}

export function ReportEditor({ report, values, onChange }: { report: Report; values: ReportEdits; onChange: (field: EditableField, text: string) => void }) {
  const fields = Object.keys(values) as EditableField[];
  const [active, setActive] = useState<EditableField>("summary_md");
  const text = values[active] ?? "";
  const dropped = droppedCitations(report[active] ?? "", text);
  const panel = "min-h-0 rounded-md border border-line bg-elevated";

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-2" role="tablist" aria-label="Report field">
        {fields.map((f) => (
          <button key={f} type="button" role="tab" aria-selected={active === f} onClick={() => setActive(f)} className={`rounded-md border px-3 py-1 text-sm ${active === f ? "border-accent text-primary" : "border-line text-secondary hover:text-primary"}`}>
            {LABEL[f]}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted">Keep the EVD- citations: every claim must cite its evidence.</span>
      </div>
      {dropped.length > 0 && (
        <div role="status" className="flex shrink-0 items-center gap-2 rounded-md border border-risk-medium/40 bg-risk-medium/10 px-3 py-1.5 text-xs text-risk-medium">
          <AlertTriangle size={13} aria-hidden /> {dropped.length} citation(s) removed from this field: <span className="num">{dropped.join(", ")}</span>
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
        <label className="flex min-h-0 flex-col text-xs text-secondary">
          <span className="mb-1">{LABEL[active]} (Markdown)</span>
          <textarea value={text} onChange={(e) => onChange(active, e.target.value)} spellCheck className={`${panel} num flex-1 resize-none p-3 text-xs leading-relaxed text-primary`} />
        </label>
        <div className="flex min-h-0 flex-col text-xs text-secondary">
          <span className="mb-1">Preview</span>
          <div className={`${panel} flex-1 overflow-y-auto p-4`}>
            {active === "customer_query_md" ? <div className="text-sm leading-relaxed whitespace-pre-wrap text-secondary">{text}</div> : <Markdown text={text} />}
          </div>
        </div>
      </div>
    </div>
  );
}

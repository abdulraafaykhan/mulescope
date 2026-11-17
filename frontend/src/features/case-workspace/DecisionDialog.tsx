/**
 * Dialogs for the decisions that need input: Edit (report text), Override
 * (new disposition + required reason) and Reject (required reason). The API
 * enforces the same rules; the UI just makes them obvious.
 */
import { useState } from "react";
import type { DecisionRequest, Disposition, Report } from "../../types/api";
import { Dialog } from "../../components/ui/overlays";
import { Button } from "../../components/ui/primitives";
import { DISPOSITION_LABEL } from "../../lib/format";

export type DialogKind = "edit" | "override" | "reject";

const TITLE: Record<DialogKind, string> = { edit: "Edit report and approve", override: "Override the policy", reject: "Reject the recommendation" };
const DISPOSITIONS: Disposition[] = ["close", "escalate", "str_draft"];

const fieldClass = "w-full rounded-md border border-line bg-elevated p-2 text-sm text-primary placeholder:text-muted";

export function DecisionDialog({ kind, report, policyDisposition, pending, onClose, onSubmit }: { kind: DialogKind; report: Report | null; policyDisposition: Disposition | null; pending: boolean; onClose: () => void; onSubmit: (body: DecisionRequest) => void }) {
  const [reason, setReason] = useState("");
  const [summary, setSummary] = useState(report?.summary_md ?? "");
  const [strText, setStrText] = useState(report?.str_narrative_md ?? "");
  const [disp, setDisp] = useState<Disposition>(DISPOSITIONS.find((d) => d !== policyDisposition) ?? "escalate");

  const needsReason = kind !== "edit";
  const valid = !needsReason || reason.trim().length > 0;

  const submit = () => {
    if (kind === "edit") {
      const edits: Record<string, string> = { summary_md: summary };
      if (report?.str_narrative_md != null) edits.str_narrative_md = strText;
      onSubmit({ decision: "edit", edits });
    } else if (kind === "override") {
      onSubmit({ decision: "override", override_disposition: disp, reason });
    } else {
      onSubmit({ decision: "reject", reason });
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={TITLE[kind]}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant={kind === "reject" ? "danger" : "primary"} disabled={!valid || pending} onClick={submit}>
            {kind === "edit" ? "Save and approve" : kind === "override" ? "Override" : "Reject"}
          </Button>
        </>
      }
    >
      {kind === "edit" && (
        <div className="space-y-3">
          <label className="block text-xs text-secondary">
            Summary (keep the EVD- citations)
            <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={12} className={`${fieldClass} num mt-1 text-xs`} />
          </label>
          {report?.str_narrative_md != null && (
            <label className="block text-xs text-secondary">
              STR narrative
              <textarea value={strText} onChange={(e) => setStrText(e.target.value)} rows={8} className={`${fieldClass} num mt-1 text-xs`} />
            </label>
          )}
        </div>
      )}
      {kind === "override" && (
        <div className="space-y-3">
          <p className="text-sm text-secondary">
            The policy recommends <strong className="text-primary">{policyDisposition ? DISPOSITION_LABEL[policyDisposition] : "—"}</strong>. Only an analyst can override it, and the reason is written to the decision record and the audit log.
          </p>
          <fieldset className="flex gap-2">
            <legend className="mb-1 text-xs text-secondary">New disposition</legend>
            {DISPOSITIONS.map((d) => (
              <label key={d} className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm ${disp === d ? "border-accent text-primary" : "border-line text-secondary"}`}>
                <input type="radio" name="disp" value={d} checked={disp === d} onChange={() => setDisp(d)} className="accent-[var(--c-accent)]" />
                {DISPOSITION_LABEL[d]}
              </label>
            ))}
          </fieldset>
        </div>
      )}
      {needsReason && (
        <label className="mt-3 block text-xs text-secondary">
          Reason (required)
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className={`${fieldClass} mt-1`} placeholder="Why are you deviating from the recommendation?" />
        </label>
      )}
    </Dialog>
  );
}

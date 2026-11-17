/**
 * Sticky case header: id, status, SLA timer, score gauge, recommendation and
 * the analyst decisions (Approve, Edit, Override, Request more, Reject). The
 * decisions are enabled only while the run waits at the analyst gate.
 */
import { useState } from "react";
import { Link } from "react-router";
import { ArrowLeft, Check, Clock, MessageSquarePlus, Pencil, Play, Radio, Scale, X } from "lucide-react";
import type { CaseDetail, Report } from "../../types/api";
import type { StreamState } from "../../lib/useRunStream";
import { useDecision, useStartRun } from "../../lib/queries";
import { Button } from "../../components/ui/primitives";
import { CaseStatusChip, Chip, DispositionChip, PriorityBadge } from "../../components/ui/chips";
import { ScoreGauge } from "../../components/ui/ScoreGauge";
import { istDateTime, relative } from "../../lib/format";
import { DecisionDialog, type DialogKind } from "./DecisionDialog";

const STREAM_LABEL: Record<StreamState, string> = { idle: "", connecting: "connecting", open: "live", reconnecting: "reconnecting", closed: "" };

export function CaseHeader({ detail, report, streamState }: { detail: CaseDetail; report: Report | null; streamState: StreamState }) {
  const { case: c, run, account } = detail;
  const start = useStartRun(c.id);
  const decision = useDecision(c.id);
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const waiting = run?.status === "awaiting_decision";
  const running = run?.status === "running";
  const canStart = !running && !waiting;
  const breached = c.sla_due_at && new Date(c.sla_due_at).getTime() < Date.now() && !["closed", "escalated", "str_drafted"].includes(c.status);
  const error = start.error ?? decision.error;
  const finalDisp = c.final_disposition;

  return (
    <div className="no-print sticky top-0 z-20 flex shrink-0 items-center justify-between gap-4 border-b border-line bg-panel px-4 py-2">
      <div className="flex min-w-0 items-center gap-4">
        <Link to="/" className="rounded p-1 text-secondary hover:bg-elevated" aria-label="Back to queue">
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="num text-lg font-semibold">{c.id}</h1>
            <PriorityBadge value={c.priority} />
            <CaseStatusChip value={c.status} />
            {STREAM_LABEL[streamState] && (
              <Chip color={streamState === "open" ? "var(--c-risk-low)" : "var(--c-risk-medium)"} icon={<Radio size={12} aria-hidden />}>
                {STREAM_LABEL[streamState]}
              </Chip>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-xs text-muted">
            <span className="truncate">{account.holder_name} · <span className="num">{account.account_no_masked}</span></span>
            <span className="num">{detail.alert.rule_id}</span>
            <span className="flex items-center gap-1" style={{ color: breached ? "var(--c-risk-critical)" : undefined }} title={istDateTime(c.sla_due_at)}>
              <Clock size={12} aria-hidden /> SLA {relative(c.sla_due_at)}
            </span>
            {run && <span className="num">{run.id} · {run.llm_mode}</span>}
          </div>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <ScoreGauge score={c.score} size={52} />
        <div className="flex flex-col items-start gap-1">
          <span className="text-[11px] text-muted uppercase">Recommended</span>
          <DispositionChip value={c.recommended_disposition} />
        </div>
        {finalDisp && (
          <div className="flex flex-col items-start gap-1">
            <span className="text-[11px] text-muted uppercase">Final</span>
            <DispositionChip value={finalDisp} />
          </div>
        )}
        <div className="mx-1 h-8 w-px bg-line" aria-hidden />
        {canStart ? (
          <Button variant="primary" onClick={() => start.mutate()} disabled={start.isPending}>
            <Play size={14} aria-hidden /> {run ? "Re-run investigation" : "Start investigation"}
          </Button>
        ) : (
          <div className="flex items-center gap-1.5">
            <Button variant="primary" disabled={!waiting || decision.isPending} onClick={() => decision.mutate({ decision: "approve" })} title="Approve the recommended disposition">
              <Check size={14} aria-hidden /> Approve
            </Button>
            <Button disabled={!waiting || !report} onClick={() => setDialog("edit")}><Pencil size={14} aria-hidden /> Edit</Button>
            <Button disabled={!waiting} onClick={() => setDialog("override")}><Scale size={14} aria-hidden /> Override</Button>
            <Button disabled={!waiting || decision.isPending} onClick={() => decision.mutate({ decision: "request_more" })}><MessageSquarePlus size={14} aria-hidden /> Request more</Button>
            <Button variant="danger" disabled={!waiting} onClick={() => setDialog("reject")}><X size={14} aria-hidden /> Reject</Button>
          </div>
        )}
      </div>
      {error && <div role="alert" className="absolute top-full right-4 mt-1 rounded-md border border-risk-critical/50 bg-panel px-3 py-1.5 text-xs text-risk-critical shadow-lg">{error.message}</div>}
      {dialog && (
        <DecisionDialog
          kind={dialog}
          report={report}
          policyDisposition={c.recommended_disposition}
          pending={decision.isPending}
          onClose={() => setDialog(null)}
          onSubmit={(body) => decision.mutate(body, { onSuccess: () => setDialog(null) })}
        />
      )}
    </div>
  );
}

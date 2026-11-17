/**
 * Actions panel: proposed actions with per-item approve / reject (reason
 * required) and reverse for executed reversible actions, plus bulk approve.
 * Nothing executes here: execution happens (mocked) after the analyst decision,
 * and rejected actions are skipped. No autonomous holds.
 */
import { useState } from "react";
import { Check, ChevronDown, ChevronRight, RotateCcw, ShieldQuestion, X } from "lucide-react";
import type { Action } from "../../types/api";
import { usePatchAction } from "../../lib/queries";
import { Button, Empty, Panel, SkeletonRows } from "../../components/ui/primitives";
import { ActionStatusChip } from "../../components/ui/chips";
import { humanize, istDate, istDateTime, maskAccount } from "../../lib/format";
import { EvdChip } from "../case-workspace/EvdChip";

const MAX_CHIPS = 4;

function ReasonInput({ label, onSubmit, onCancel, pending }: { label: string; onSubmit: (reason: string) => void; onCancel: () => void; pending: boolean }) {
  const [reason, setReason] = useState("");
  return (
    <div className="mt-2 flex gap-1">
      <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder={`${label} reason (required)`} aria-label={`${label} reason`} className="h-7 min-w-0 flex-1 rounded-md border border-line bg-elevated px-2 text-xs text-primary placeholder:text-muted" />
      <Button size="sm" variant="danger" disabled={!reason.trim() || pending} onClick={() => onSubmit(reason)}>{label}</Button>
      <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
    </div>
  );
}

function ActionItem({ action, caseId }: { action: Action; caseId: string }) {
  const patch = usePatchAction(caseId);
  const [mode, setMode] = useState<"reject" | "reverse" | null>(null);
  const [open, setOpen] = useState(false);
  const target = action.target.split(",").map((t) => (t.startsWith("ACC-") ? t : maskAccount(t))).join(", ");
  const send = (op: "approve" | "reject" | "reverse", reason?: string) => patch.mutate({ id: action.id, body: { op, reason: reason ?? null } }, { onSuccess: () => setMode(null) });

  return (
    <li className="border-b border-line/60 px-3 py-2 last:border-0">
      <div className="flex items-start justify-between gap-2">
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex min-w-0 items-start gap-1 text-left">
          {open ? <ChevronDown size={12} className="mt-1 shrink-0 text-muted" aria-hidden /> : <ChevronRight size={12} className="mt-1 shrink-0 text-muted" aria-hidden />}
          <span className="min-w-0">
            <span className="block text-sm font-medium text-primary">{humanize(action.type)}</span>
            <span className="num block truncate text-[11px] text-muted">{target} · {action.owner_role} · due {istDate(action.due_at)}</span>
          </span>
        </button>
        <ActionStatusChip value={action.status} />
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1 pl-4 text-[11px] text-muted">
        {action.requires_approval && <span className="flex items-center gap-0.5 rounded border border-risk-medium/40 px-1 text-risk-medium"><ShieldQuestion size={10} aria-hidden />needs approval</span>}
        <span className="rounded border border-line px-1">{action.reversible ? "reversible" : "irreversible"}</span>
        {action.evidence_ids.slice(0, MAX_CHIPS).map((id) => <EvdChip key={id} id={id} originRunId={action.run_id} />)}
        {action.evidence_ids.length > MAX_CHIPS && <span>+{action.evidence_ids.length - MAX_CHIPS}</span>}
      </div>
      {open && (
        <div className="mt-2 space-y-1 pl-4 text-xs">
          <p className="text-secondary">{action.description}</p>
          <p className="num text-muted">rule {action.rule} · tool {action.mock_tool}</p>
          {action.result && <p className="text-risk-low">{action.result.message}</p>}
          <ol className="mt-1 border-l border-line pl-2">
            {action.history.map((h, i) => (
              <li key={i} className="text-muted"><span className="num">{istDateTime(h.ts)}</span> · {h.status} by {h.by}{h.reason ? ` — ${h.reason}` : ""}</li>
            ))}
          </ol>
        </div>
      )}
      {mode === null && (
        <div className="mt-2 flex gap-1 pl-4">
          {action.status === "proposed" && <Button size="sm" variant="success" disabled={patch.isPending} onClick={() => send("approve")}><Check size={12} aria-hidden /> Approve</Button>}
          {(action.status === "proposed" || action.status === "approved") && <Button size="sm" variant="danger" onClick={() => setMode("reject")}><X size={12} aria-hidden /> Reject</Button>}
          {action.status === "executed" && action.reversible && <Button size="sm" onClick={() => setMode("reverse")}><RotateCcw size={12} aria-hidden /> Reverse</Button>}
        </div>
      )}
      {mode && <div className="pl-4"><ReasonInput label={mode === "reject" ? "Reject" : "Reverse"} pending={patch.isPending} onCancel={() => setMode(null)} onSubmit={(r) => send(mode, r)} /></div>}
      {patch.error && <p role="alert" className="mt-1 pl-4 text-xs text-risk-critical">{patch.error.message}</p>}
    </li>
  );
}

export function ActionsPanel({ caseId, actions, loading }: { caseId: string; actions: Action[]; loading: boolean }) {
  const patch = usePatchAction(caseId);
  const proposed = actions.filter((a) => a.status === "proposed");
  const approveAll = async () => {
    for (const a of proposed) await patch.mutateAsync({ id: a.id, body: { op: "approve" } });
  };
  return (
    <Panel
      title={`Actions (${actions.length})`}
      actions={proposed.length > 1 ? <Button size="sm" variant="ghost" disabled={patch.isPending} onClick={() => void approveAll()}><Check size={12} aria-hidden /> Approve all {proposed.length}</Button> : undefined}
    >
      {loading && <SkeletonRows rows={4} />}
      {!loading && actions.length === 0 && <Empty>The action planner proposes actions after scoring.</Empty>}
      <ul>{actions.map((a) => <ActionItem key={a.id} action={a} caseId={caseId} />)}</ul>
    </Panel>
  );
}

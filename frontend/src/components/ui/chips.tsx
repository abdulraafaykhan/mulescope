/**
 * Status chips. Colour is never the only signal: every chip has an icon and text.
 */
import type { ReactNode } from "react";
import { AlertOctagon, ArrowUpRight, CheckCircle2, CircleDashed, Clock, FileWarning, Loader2, RotateCcw, ShieldCheck, XCircle } from "lucide-react";
import type { ActionStatus, CaseStatus, Disposition } from "../../types/api";
import { ACTION_STATUS_COLOR, CASE_STATUS_COLOR, DISPOSITION_COLOR } from "../../lib/meta";
import { DISPOSITION_LABEL, humanize } from "../../lib/format";

export function Chip({ color, icon, children, title }: { color: string; icon?: ReactNode; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs font-medium whitespace-nowrap"
      style={{ color, borderColor: `color-mix(in srgb, ${color} 45%, transparent)`, background: `color-mix(in srgb, ${color} 12%, transparent)` }}
    >
      {icon}
      {children}
    </span>
  );
}

const DISP_ICON: Record<Disposition, ReactNode> = {
  close: <ShieldCheck size={12} aria-hidden />,
  escalate: <ArrowUpRight size={12} aria-hidden />,
  str_draft: <FileWarning size={12} aria-hidden />,
};

export function DispositionChip({ value }: { value: Disposition | null | undefined }) {
  if (!value) return <Chip color="var(--c-text-muted)" icon={<CircleDashed size={12} aria-hidden />}>Not scored</Chip>;
  return (
    <Chip color={DISPOSITION_COLOR[value]} icon={DISP_ICON[value]}>
      {DISPOSITION_LABEL[value]}
    </Chip>
  );
}

const CASE_ICON: Record<CaseStatus, ReactNode> = {
  new: <CircleDashed size={12} aria-hidden />,
  investigating: <Loader2 size={12} className="animate-spin" aria-hidden />,
  awaiting_decision: <Clock size={12} aria-hidden />,
  closed: <CheckCircle2 size={12} aria-hidden />,
  escalated: <ArrowUpRight size={12} aria-hidden />,
  str_drafted: <AlertOctagon size={12} aria-hidden />,
  returned: <RotateCcw size={12} aria-hidden />,
};

export function CaseStatusChip({ value }: { value: CaseStatus }) {
  return (
    <Chip color={CASE_STATUS_COLOR[value]} icon={CASE_ICON[value]}>
      {humanize(value)}
    </Chip>
  );
}

const ACTION_ICON: Record<ActionStatus, ReactNode> = {
  proposed: <CircleDashed size={12} aria-hidden />,
  approved: <CheckCircle2 size={12} aria-hidden />,
  rejected: <XCircle size={12} aria-hidden />,
  executed: <ShieldCheck size={12} aria-hidden />,
  completed: <ShieldCheck size={12} aria-hidden />,
  reversed: <RotateCcw size={12} aria-hidden />,
  cancelled: <XCircle size={12} aria-hidden />,
};

export function ActionStatusChip({ value }: { value: ActionStatus }) {
  return (
    <Chip color={ACTION_STATUS_COLOR[value]} icon={ACTION_ICON[value]}>
      {humanize(value)}
    </Chip>
  );
}

/** Priority 1 is the most urgent. */
export function PriorityBadge({ value }: { value: number }) {
  const color = value <= 1 ? "var(--c-risk-critical)" : value === 2 ? "var(--c-risk-high)" : "var(--c-risk-medium)";
  return (
    <span className="num inline-flex items-center gap-1 text-xs font-semibold" style={{ color }}>
      <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: color }} />P{value}
    </span>
  );
}

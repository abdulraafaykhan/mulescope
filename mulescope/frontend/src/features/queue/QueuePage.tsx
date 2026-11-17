/**
 * Alert queue (home): KPI strip, filter bar and the case table. Row click (or
 * Enter on a focused row) opens the case workspace.
 */
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { AlertTriangle, Bot, Clock, FolderOpen, Search, UserCheck } from "lucide-react";
import { useQueue } from "../../lib/queries";
import type { Disposition, QueueRow } from "../../types/api";
import { Empty, ErrorState, Panel, SkeletonRows } from "../../components/ui/primitives";
import { CaseStatusChip, DispositionChip, PriorityBadge } from "../../components/ui/chips";
import { ScoreGauge } from "../../components/ui/ScoreGauge";
import { inrShort, int, istDateTime, relative } from "../../lib/format";

const STATUSES = ["", "new", "investigating", "awaiting_decision", "escalated", "str_drafted", "closed", "returned"];
const PRIORITIES = ["", "1", "2", "3"];
const DISPOSITIONS: ("" | Disposition)[] = ["", "str_draft", "escalate", "close"];

function Kpi({ label, value, icon, color }: { label: string; value: number | undefined; icon: ReactNode; color: string }) {
  return (
    <div className="flex items-center gap-3 rounded-[8px] border border-line bg-panel px-4 py-3">
      <span className="flex h-8 w-8 items-center justify-center rounded-md" style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
        {icon}
      </span>
      <div>
        <div className="num text-xl font-semibold">{value ?? "—"}</div>
        <div className="text-xs text-secondary">{label}</div>
      </div>
    </div>
  );
}

function Select({ label, value, options, onChange, format }: { label: string; value: string; options: string[]; onChange: (v: string) => void; format?: (v: string) => string }) {
  return (
    <label className="flex items-center gap-2 text-xs text-secondary">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="h-8 rounded-md border border-line bg-elevated px-2 text-sm text-primary">
        {options.map((o) => (
          <option key={o} value={o}>
            {o ? (format ? format(o) : o) : "All"}
          </option>
        ))}
      </select>
    </label>
  );
}

function SlaCell({ row }: { row: QueueRow }) {
  if (!row.sla_due_at) return <span className="text-muted">—</span>;
  const open = !["closed", "escalated", "str_drafted"].includes(row.status);
  const breached = open && new Date(row.sla_due_at).getTime() < Date.now();
  return (
    <span className="num flex items-center gap-1 text-xs" style={{ color: breached ? "var(--c-risk-critical)" : open ? "var(--c-text-primary)" : "var(--c-text-muted)" }} title={istDateTime(row.sla_due_at)}>
      {breached ? <AlertTriangle size={12} aria-hidden /> : <Clock size={12} aria-hidden />}
      {open ? relative(row.sla_due_at) : "done"}
    </span>
  );
}

export function QueuePage() {
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [disposition, setDisposition] = useState("");
  const [search, setSearch] = useState("");
  const queue = useQueue(status, priority);
  const navigate = useNavigate();

  const rows = useMemo(() => {
    const items = queue.data?.items ?? [];
    const q = search.trim().toLowerCase();
    return items.filter((r) => {
      if (disposition && r.recommended_disposition !== disposition) return false;
      if (!q) return true;
      return [r.case_id, r.account_id, r.holder_name, r.customer_name, r.account_masked].some((v) => v?.toLowerCase().includes(q));
    });
  }, [queue.data, disposition, search]);

  const k = queue.data?.kpis;
  return (
    <div className="mx-auto flex h-full max-w-[1600px] flex-col gap-4 overflow-hidden p-4">
      <div className="grid shrink-0 grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Open cases" value={k?.open_cases} icon={<FolderOpen size={16} />} color="var(--c-accent)" />
        <Kpi label="SLA breaching" value={k?.sla_breaching} icon={<AlertTriangle size={16} />} color="var(--c-risk-critical)" />
        <Kpi label="Awaiting decision" value={k?.awaiting_decision} icon={<UserCheck size={16} />} color="var(--c-risk-medium)" />
        <Kpi label="Fallback runs" value={k?.fallback_runs} icon={<Bot size={16} />} color="var(--c-agent-code)" />
        <Kpi label="Total cases" value={k?.total_cases} icon={<FolderOpen size={16} />} color="var(--c-role-receiver)" />
      </div>

      <Panel
        className="flex min-h-0 flex-1 flex-col"
        bodyClass="min-h-0 flex-1 overflow-auto"
        title={`Cases (${rows.length})`}
        actions={
          <div className="flex items-center gap-3 py-1">
            <label className="relative">
              <Search size={13} className="absolute top-2 left-2 text-muted" aria-hidden />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Case, account, name" aria-label="Search cases" className="h-7 w-52 rounded-md border border-line bg-elevated pr-2 pl-7 text-sm text-primary placeholder:text-muted" />
            </label>
            <Select label="Priority" value={priority} options={PRIORITIES} onChange={setPriority} format={(v) => `P${v}`} />
            <Select label="Status" value={status} options={STATUSES} onChange={setStatus} format={(v) => v.replace(/_/g, " ")} />
            <Select label="Recommendation" value={disposition} options={DISPOSITIONS} onChange={setDisposition} format={(v) => v.replace("_", " ")} />
          </div>
        }
      >
        {queue.isLoading && <SkeletonRows rows={12} />}
        {queue.isError && <ErrorState error={queue.error} />}
        {queue.data && rows.length === 0 && <Empty>No cases match these filters. Seed data with `uv run seed --seed 42 --customers 300 --reset`.</Empty>}
        {rows.length > 0 && (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-elevated text-left text-xs text-secondary">
              <tr>
                {["Case", "Pri", "Account", "Customer", "Window inflow", "Senders", "Score", "Recommendation", "SLA", "Status", "Assignee"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.case_id}
                  tabIndex={0}
                  onClick={() => navigate(`/cases/${r.case_id}`)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(`/cases/${r.case_id}`)}
                  className="cursor-pointer border-b border-line/60 hover:bg-elevated/70 focus:bg-elevated"
                >
                  <td className="num px-3 py-1.5 text-accent">{r.case_id}</td>
                  <td className="px-3 py-1.5"><PriorityBadge value={r.priority} /></td>
                  <td className="num px-3 py-1.5 text-secondary">{r.account_masked}</td>
                  <td className="px-3 py-1.5">
                    <div className="max-w-[220px] truncate">{r.customer_name ?? r.holder_name}</div>
                    <div className="text-xs text-muted">{r.occupation}</div>
                  </td>
                  <td className="num px-3 py-1.5 text-right">{inrShort(r.inflow)}</td>
                  <td className="num px-3 py-1.5 text-right">{int(r.senders)}</td>
                  <td className="px-3 py-1.5"><ScoreGauge score={r.score} size={38} /></td>
                  <td className="px-3 py-1.5"><DispositionChip value={r.recommended_disposition} /></td>
                  <td className="px-3 py-1.5"><SlaCell row={r} /></td>
                  <td className="px-3 py-1.5"><CaseStatusChip value={r.status} /></td>
                  <td className="px-3 py-1.5 text-xs text-muted">{r.assigned_to ?? "Unassigned"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

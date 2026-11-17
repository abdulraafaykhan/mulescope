/**
 * Bottom drawer of the case workspace with two tabs: Audit log and
 * Diagnostics. Collapsed by default to a tab bar so the workspace keeps its
 * height; opening it does not shift the columns above (fixed height).
 */
import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp, ScrollText, Stethoscope } from "lucide-react";
import { Tabs } from "../../components/ui/overlays";
import { AuditLog } from "./AuditLog";
import { DiagnosticsView } from "./DiagnosticsView";

type Tab = "audit" | "diagnostics";
const TABS: { id: Tab; label: ReactNode }[] = [
  { id: "audit", label: <><ScrollText size={14} aria-hidden /> Audit log</> },
  { id: "diagnostics", label: <><Stethoscope size={14} aria-hidden /> Diagnostics</> },
];

export function BottomDrawer({ caseId, runId, runActive }: { caseId: string; runId: string | null; runActive: boolean }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("audit");
  return (
    <div className="no-print shrink-0 border-t border-line bg-panel">
      <Tabs
        tabs={TABS}
        value={tab}
        onChange={(t) => {
          setTab(t);
          setOpen(true);
        }}
        right={
          <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-1 rounded px-2 py-1 text-xs text-secondary hover:bg-elevated" aria-expanded={open}>
            {open ? <ChevronDown size={14} aria-hidden /> : <ChevronUp size={14} aria-hidden />}
            {open ? "Hide" : "Show"}
          </button>
        }
      />
      {open && (
        <div className="h-[300px] overflow-hidden">
          {tab === "audit" ? <AuditLog caseId={caseId} runActive={runActive} /> : <DiagnosticsView runId={runId} runActive={runActive} />}
        </div>
      )}
    </div>
  );
}

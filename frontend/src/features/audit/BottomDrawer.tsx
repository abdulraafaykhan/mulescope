/**
 * Bottom drawer of the case workspace with two tabs: Audit log and
 * Diagnostics. Collapsed by default to a tab bar. When open it takes real
 * space in the page (the columns above shrink, nothing is covered) and its
 * height is dragged with the handle on its top edge, or set with the arrow
 * keys on that handle. The height is capped so the workspace stays usable.
 */
import { useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { ChevronDown, ChevronUp, ScrollText, Stethoscope } from "lucide-react";
import { Tabs } from "../../components/ui/overlays";
import { AuditLog } from "./AuditLog";
import { DiagnosticsView } from "./DiagnosticsView";

type Tab = "audit" | "diagnostics";
const TABS: { id: Tab; label: ReactNode }[] = [
  { id: "audit", label: <><ScrollText size={14} aria-hidden /> Audit log</> },
  { id: "diagnostics", label: <><Stethoscope size={14} aria-hidden /> Diagnostics</> },
];

const DEFAULT_HEIGHT = 300;
const MIN_HEIGHT = 160;
// Share of the workspace height the drawer may take, so the columns keep room.
const MAX_SHARE = 0.6;
const KEY_STEP = 32;

export function BottomDrawer({ caseId, runId, runActive }: { caseId: string; runId: string | null; runActive: boolean }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("audit");
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const rootRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ y: number; h: number } | null>(null);

  const maxHeight = () => (rootRef.current?.parentElement?.clientHeight ?? window.innerHeight) * MAX_SHARE;
  const clamp = (h: number) => Math.round(Math.max(MIN_HEIGHT, Math.min(h, maxHeight())));

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { y: e.clientY, h: height };
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current) setHeight(clamp(drag.current.h + drag.current.y - e.clientY));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowUp") setHeight((h) => clamp(h + KEY_STEP));
    else if (e.key === "ArrowDown") setHeight((h) => clamp(h - KEY_STEP));
    else return;
    e.preventDefault();
  };

  return (
    <div ref={rootRef} className="no-print relative shrink-0 border-t border-line bg-panel">
      {open && (
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize the audit and diagnostics panel"
          aria-valuenow={height}
          aria-valuemin={MIN_HEIGHT}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={() => (drag.current = null)}
          onKeyDown={onKeyDown}
          className="group absolute -top-1.5 right-0 left-0 z-10 flex h-3 cursor-row-resize touch-none items-center justify-center"
        >
          <span className="h-1 w-12 rounded-full bg-line transition group-hover:bg-accent group-focus-visible:bg-accent" aria-hidden />
        </div>
      )}
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
        <div className="overflow-hidden" style={{ height }}>
          {tab === "audit" ? <AuditLog caseId={caseId} runActive={runActive} /> : <DiagnosticsView runId={runId} runActive={runActive} />}
        </div>
      )}
    </div>
  );
}

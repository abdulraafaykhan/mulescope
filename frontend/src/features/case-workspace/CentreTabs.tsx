/**
 * The four centre tabs of the case workspace (money flow, timeline,
 * transactions, report). Rendered inline in the centre column and, through the
 * expand control, again near full screen in a large view, so each view can be
 * read at a useful size. Only one copy shows content at a time.
 */
import { lazy, Suspense, type ReactNode } from "react";
import { FileText, GitBranch, LineChart, Table } from "lucide-react";
import type { CaseDetail, Report } from "../../types/api";
import { SkeletonRows } from "../../components/ui/primitives";
import { Tabs } from "../../components/ui/overlays";
import { TimelineTab } from "./TimelineTab";
import { TransactionsTab } from "./TransactionsTab";
import { ReportTab } from "./ReportTab";

const MoneyFlow = lazy(() => import("../flow-graph/MoneyFlow"));

export type CentreTab = "flow" | "timeline" | "transactions" | "report";

const TABS: { id: CentreTab; label: ReactNode }[] = [
  { id: "flow", label: <><GitBranch size={14} aria-hidden /> Money flow</> },
  { id: "timeline", label: <><LineChart size={14} aria-hidden /> Timeline</> },
  { id: "transactions", label: <><Table size={14} aria-hidden /> Transactions</> },
  { id: "report", label: <><FileText size={14} aria-hidden /> Report</> },
];

interface Props {
  tab: CentreTab;
  onTab: (tab: CentreTab) => void;
  caseId: string;
  detail: CaseDetail;
  report: Report | null;
  reportLoading: boolean;
  /** Expand or close control at the right of the tab bar. */
  action: ReactNode;
  /** Shown instead of the content (while the large view is open). */
  placeholder?: ReactNode;
}

export function CentreTabs({ tab, onTab, caseId, detail, report, reportLoading, action, placeholder }: Props) {
  return (
    <>
      <Tabs tabs={TABS} value={tab} onChange={onTab} right={action} />
      <div className="min-h-0 flex-1 overflow-hidden">
        {placeholder ?? (
          <>
            {tab === "flow" && (
              <Suspense fallback={<SkeletonRows rows={8} />}>
                <MoneyFlow caseId={caseId} />
              </Suspense>
            )}
            {tab === "timeline" && <TimelineTab caseId={caseId} />}
            {tab === "transactions" && <TransactionsTab caseId={caseId} />}
            {tab === "report" && <ReportTab report={report} loading={reportLoading} detail={detail} />}
          </>
        )}
      </div>
    </>
  );
}

/** Small text button for the tab bar (expand, close). */
export function TabBarButton({ onClick, icon, children, title }: { onClick: () => void; icon: ReactNode; children: ReactNode; title: string }) {
  return (
    <button type="button" onClick={onClick} title={title} className="flex items-center gap-1 rounded px-2 py-1 text-xs whitespace-nowrap text-secondary hover:bg-elevated hover:text-primary">
      {icon}
      {children}
    </button>
  );
}

/**
 * Case workspace (section 9.3): sticky header, entity strip, left column
 * (score breakdown, evidence), centre tabs (flow, timeline, transactions,
 * report), right column (agents, actions) and the bottom drawer (audit,
 * diagnostics). This container owns the data hooks and passes data down.
 */
import { lazy, Suspense, useState, type ReactNode } from "react";
import { useParams } from "react-router";
import { FileText, GitBranch, LineChart, Table } from "lucide-react";
import { useActions, useCase, useEvidence, useReport } from "../../lib/queries";
import { useRunStream } from "../../lib/useRunStream";
import { ErrorState, Panel, Skeleton, SkeletonRows } from "../../components/ui/primitives";
import { Tabs } from "../../components/ui/overlays";
import { EvidenceProvider } from "./EvidenceContext";
import { CaseHeader } from "./CaseHeader";
import { EntityStrip } from "./EntityStrip";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { EvidenceList } from "./EvidenceList";
import { TimelineTab } from "./TimelineTab";
import { TransactionsTab } from "./TransactionsTab";
import { ReportTab } from "./ReportTab";
import { AgentsPanel } from "../agents/AgentsPanel";
import { ActionsPanel } from "../actions/ActionsPanel";
import { BottomDrawer } from "../audit/BottomDrawer";

const MoneyFlow = lazy(() => import("../flow-graph/MoneyFlow"));

type Tab = "flow" | "timeline" | "transactions" | "report";

const TABS: { id: Tab; label: ReactNode }[] = [
  { id: "flow", label: <><GitBranch size={14} aria-hidden /> Money flow</> },
  { id: "timeline", label: <><LineChart size={14} aria-hidden /> Timeline</> },
  { id: "transactions", label: <><Table size={14} aria-hidden /> Transactions</> },
  { id: "report", label: <><FileText size={14} aria-hidden /> Report</> },
];

export default function CaseWorkspace() {
  const { caseId = "" } = useParams();
  const detail = useCase(caseId);
  const run = detail.data?.run ?? null;
  const runActive = run?.status === "running" || run?.status === "awaiting_decision";
  const evidence = useEvidence(caseId);
  const actions = useActions(caseId);
  const report = useReport(caseId, Boolean(run));
  const stream = useRunStream(caseId, run?.id, runActive);
  const [tab, setTab] = useState<Tab>("flow");

  if (detail.isError) return <ErrorState error={detail.error} />;
  if (!detail.data) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-28 w-full" />
        <SkeletonRows rows={10} />
      </div>
    );
  }
  const d = detail.data;

  return (
    <EvidenceProvider evidence={evidence.data ?? []}>
      <div className="flex h-full flex-col">
        <CaseHeader detail={d} report={report.data ?? null} streamState={stream.state} />
        <div className="shrink-0 px-3 pt-3">
          <EntityStrip strip={d.entity_strip} customer={d.customer} account={d.account} windowStart={d.alert.window.start} />
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_340px] gap-3 p-3">
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <ScoreBreakdown evidence={evidence.data ?? []} score={d.case.score} typologies={d.case.typologies ?? []} loading={evidence.isLoading} />
            <EvidenceList evidence={evidence.data ?? []} loading={evidence.isLoading} hasRun={Boolean(run)} />
          </div>
          <Panel className="flex min-h-0 flex-col" bodyClass="flex min-h-0 flex-1 flex-col">
            <Tabs tabs={TABS} value={tab} onChange={setTab} />
            <div className="min-h-0 flex-1">
              {tab === "flow" && (
                <Suspense fallback={<SkeletonRows rows={8} />}>
                  <MoneyFlow caseId={caseId} />
                </Suspense>
              )}
              {tab === "timeline" && <TimelineTab caseId={caseId} />}
              {tab === "transactions" && <TransactionsTab caseId={caseId} />}
              {tab === "report" && <ReportTab report={report.data ?? null} loading={report.isLoading} detail={d} />}
            </div>
          </Panel>
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <AgentsPanel run={run} events={stream.events} streamState={stream.state} />
            <ActionsPanel caseId={caseId} actions={actions.data ?? []} loading={actions.isLoading} />
          </div>
        </div>
        <BottomDrawer caseId={caseId} runId={run?.id ?? null} runActive={runActive} />
      </div>
    </EvidenceProvider>
  );
}

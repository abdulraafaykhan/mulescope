/**
 * Case workspace (section 9.3): sticky header, entity strip, left column
 * (score breakdown, evidence), centre tabs (flow, timeline, transactions,
 * report), right column (agents, actions) and the bottom drawer (audit,
 * diagnostics). The centre tabs can open in a large view. The column row is
 * clipped to its own height, so the drawer below takes space instead of
 * covering it. This container owns the data hooks and passes data down.
 */
import { useCallback, useState } from "react";
import { useParams } from "react-router";
import { Maximize2, Minimize2 } from "lucide-react";
import { useActions, useCase, useEvidence, useReport } from "../../lib/queries";
import { useRunStream } from "../../lib/useRunStream";
import { Button, Empty, ErrorState, Panel, Skeleton, SkeletonRows } from "../../components/ui/primitives";
import { LargeView } from "../../components/ui/overlays";
import { EvidenceProvider } from "./EvidenceContext";
import { CaseHeader } from "./CaseHeader";
import { EntityStrip } from "./EntityStrip";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { EvidenceList } from "./EvidenceList";
import { CentreTabs, TabBarButton, type CentreTab } from "./CentreTabs";
import { AgentsPanel } from "../agents/AgentsPanel";
import { ActionsPanel } from "../actions/ActionsPanel";
import { BottomDrawer } from "../audit/BottomDrawer";

export default function CaseWorkspace() {
  const { caseId = "" } = useParams();
  const detail = useCase(caseId);
  const run = detail.data?.run ?? null;
  const runActive = run?.status === "running" || run?.status === "awaiting_decision";
  const evidence = useEvidence(caseId);
  const actions = useActions(caseId);
  const report = useReport(caseId, Boolean(run));
  const stream = useRunStream(caseId, run?.id, runActive);
  const [tab, setTab] = useState<CentreTab>("flow");
  const [large, setLarge] = useState(false);
  const closeLarge = useCallback(() => setLarge(false), []);

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
  const centre = { tab, onTab: setTab, caseId, detail: d, report: report.data ?? null, reportLoading: report.isLoading };

  return (
    <EvidenceProvider evidence={evidence.data ?? []} runId={run?.id ?? null}>
      <div className="flex h-full flex-col">
        <CaseHeader detail={d} report={report.data ?? null} streamState={stream.state} />
        <div className="shrink-0 px-3 pt-3">
          <EntityStrip strip={d.entity_strip} customer={d.customer} account={d.account} windowStart={d.alert.window.start} />
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_340px] grid-rows-[minmax(0,1fr)] gap-3 overflow-hidden p-3">
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <ScoreBreakdown evidence={evidence.data ?? []} score={d.case.score} typologies={d.case.typologies ?? []} loading={evidence.isLoading} />
            <EvidenceList evidence={evidence.data ?? []} loading={evidence.isLoading} hasRun={Boolean(run)} />
          </div>
          <Panel className="flex min-h-0 flex-col overflow-hidden" bodyClass="flex min-h-0 flex-1 flex-col">
            <CentreTabs
              {...centre}
              action={<TabBarButton onClick={() => setLarge(true)} icon={<Maximize2 size={13} aria-hidden />} title="Open this view large (Esc closes)">Expand</TabBarButton>}
              placeholder={large ? <Empty>Open in the large view. <Button size="sm" variant="ghost" onClick={closeLarge}>Bring it back</Button></Empty> : undefined}
            />
          </Panel>
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <AgentsPanel run={run} events={stream.events} streamState={stream.state} />
            <ActionsPanel caseId={caseId} actions={actions.data ?? []} loading={actions.isLoading} />
          </div>
        </div>
        <BottomDrawer caseId={caseId} runId={run?.id ?? null} runActive={runActive} />
      </div>
      <LargeView open={large} onClose={closeLarge} label={`${d.case.id} large view`}>
        <CentreTabs {...centre} action={<TabBarButton onClick={closeLarge} icon={<Minimize2 size={13} aria-hidden />} title="Close the large view (Esc)">Close</TabBarButton>} />
      </LargeView>
    </EvidenceProvider>
  );
}

/**
 * Money-flow tab: senders on the left, the flagged account in the centre,
 * receivers on the right (dagre, left to right). By default each side shows
 * its top 8 parties by amount plus one aggregate card for the rest; clicking
 * the aggregate expands that side. Edge width is amount, label is count and
 * exit time, edge colour is exit speed. Hover highlights a path, click opens
 * the account drawer, and the time slider replays the window.
 */
import { useMemo, useState } from "react";
import { Background, Controls, MarkerType, MiniMap, ReactFlow, type Edge } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { useCase, useFlow } from "../../lib/queries";
import type { FlowEdge, FlowNode } from "../../types/api";
import { Button, Empty, ErrorState, SkeletonRows } from "../../components/ui/primitives";
import { ageDays, inrShort, istDateTime, minutes } from "../../lib/format";
import { exitColor } from "../../lib/meta";
import { isInternalAccount, useAccountDrawer } from "../../app/AccountDrawerContext";
import { AccountNode, MULE_H, MULE_W, PARTY_H, PARTY_W, type AccountFlowNode } from "./AccountNode";
import { collapseFlow, type Side } from "./aggregate";

const NODE_TYPES = { account: AccountNode };
const SLIDER_STEPS = 100;
// Tight spacing so nine cards per column fit the pane at 1440x900 near 1:1 zoom.
const NODE_SEP = 8;
const RANK_SEP = 80;

function layout(nodes: FlowNode[], edges: FlowEdge[]): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: NODE_SEP, ranksep: RANK_SEP });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, n.role === "mule" ? { width: MULE_W, height: MULE_H } : { width: PARTY_W, height: PARTY_H });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  const out = new Map<string, { x: number; y: number }>();
  for (const n of nodes) {
    const p = g.node(n.id);
    out.set(n.id, { x: p.x - p.width / 2, y: p.y - p.height / 2 });
  }
  return out;
}

function Legend() {
  const items: [string, string][] = [["< 30 min", exitColor(10)], ["< 90 min", exitColor(60)], ["< 1 day", exitColor(600)], ["slower", exitColor(5000)]];
  return (
    <div className="flex items-center gap-3 text-[11px] text-muted">
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-role-sender" />sender</span>
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-role-mule" />flagged</span>
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-role-receiver" />receiver</span>
      <span className="ml-1">exit:</span>
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1 whitespace-nowrap"><span className="h-0.5 w-4" style={{ background: color }} />{label}</span>
      ))}
    </div>
  );
}

export default function MoneyFlow({ caseId }: { caseId: string }) {
  const flow = useFlow(caseId);
  const detail = useCase(caseId);
  const drawer = useAccountDrawer();
  const [hover, setHover] = useState<string | null>(null);
  const [step, setStep] = useState(SLIDER_STEPS);
  const [expanded, setExpanded] = useState<Record<Side, boolean>>({ sender: false, receiver: false });

  const win = detail.data?.alert.window;
  const startMs = win ? new Date(win.start).getTime() : 0;
  const endMs = win ? new Date(win.end).getTime() : 0;
  const cutoff = startMs + ((endMs - startMs) * step) / SLIDER_STEPS;
  const view = useMemo(() => (flow.data ? collapseFlow(flow.data, expanded) : null), [flow.data, expanded]);
  const positions = useMemo(() => (view ? layout(view.nodes, view.edges) : new Map<string, { x: number; y: number }>()), [view]);
  const maxAmount = useMemo(() => Math.max(1, ...(view?.edges.map((e) => e.amount) ?? [1])), [view]);

  const { nodes, edges } = useMemo(() => {
    if (!view) return { nodes: [] as AccountFlowNode[], edges: [] as Edge[] };
    const mule = view.nodes.find((n) => n.role === "mule");
    const visible = (ts: string | null | undefined) => !ts || step >= SLIDER_STEPS || new Date(ts).getTime() <= cutoff;
    const onPath = (id: string) => !hover || hover === id || id === mule?.id;
    const nodes: AccountFlowNode[] = view.nodes.map((n) => ({
      id: n.id,
      type: "account",
      position: positions.get(n.id) ?? { x: 0, y: 0 },
      draggable: false,
      data: { flow: n, dimmed: !visible(n.first_ts) || !onPath(n.id), ageDays: n.role === "mule" ? ageDays(n.opened_at, startMs) : null, internal: isInternalAccount(n.ref), aggregate: view.aggregates.has(n.id) },
    }));
    const edges: Edge[] = view.edges.map((e) => {
      const party = e.source === mule?.id ? e.target : e.source;
      const node = view.nodes.find((n) => n.id === party);
      const dim = !visible(node?.first_ts) || (hover !== null && hover !== party && hover !== mule?.id);
      const color = e.source === mule?.id ? exitColor(e.exit_minutes) : "var(--c-role-sender)";
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: `${e.count}×${e.exit_minutes != null ? ` · ${minutes(e.exit_minutes)}` : ""}`,
        labelStyle: { fontSize: 11, fill: "var(--c-text-secondary)" },
        style: { stroke: color, strokeWidth: 1 + (e.amount / maxAmount) * 7, opacity: dim ? 0.12 : 0.85 },
        markerEnd: { type: MarkerType.ArrowClosed, color },
        animated: !dim && e.exit_minutes != null && e.exit_minutes < 30,
      };
    });
    return { nodes, edges };
  }, [view, positions, hover, step, cutoff, maxAmount, startMs]);

  if (flow.isLoading) return <SkeletonRows rows={8} />;
  if (flow.isError) return <ErrorState error={flow.error} />;
  if (!flow.data || !view || flow.data.nodes.length <= 1) return <Empty>No transactions in the alert window.</Empty>;
  const anyExpanded = expanded.sender || expanded.receiver;

  return (
    <div className="flex h-full flex-col">
      <div className="h-0 flex-1">
        <ReactFlow
          // Remount on expand/collapse so fitView frames the new layout.
          key={`${expanded.sender}-${expanded.receiver}`}
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.04, maxZoom: 1.1 }}
          minZoom={0.2}
          proOptions={{ hideAttribution: true }}
          nodesConnectable={false}
          onNodeMouseEnter={(_, n) => setHover(n.id)}
          onNodeMouseLeave={() => setHover(null)}
          onNodeClick={(_, n) => {
            const agg = view.aggregates.get(n.id);
            if (agg) {
              setExpanded((x) => ({ ...x, [agg.side]: true }));
              return;
            }
            const f = (n as AccountFlowNode).data.flow;
            if (f.role === "mule" && detail.data) drawer.open(detail.data.account.id);
            else if (isInternalAccount(f.ref)) drawer.open(f.ref);
          }}
        >
          <Background color="var(--c-border)" gap={24} />
          <Controls showInteractive={false} position="bottom-right" />
          {anyExpanded && <MiniMap pannable zoomable position="top-right" nodeColor={(n) => `var(--c-role-${(n as AccountFlowNode).data.flow.role})`} maskColor="rgba(11,15,26,0.7)" />}
        </ReactFlow>
      </div>
      <div className="flex shrink-0 items-center gap-3 border-t border-line px-3 py-2">
        <label className="flex min-w-0 flex-1 items-center gap-2 text-xs text-secondary">
          Replay
          <input type="range" min={0} max={SLIDER_STEPS} value={step} onChange={(e) => setStep(Number(e.target.value))} className="min-w-0 flex-1 accent-[var(--c-accent)]" aria-label="Replay the alert window" />
          <span className="num w-28 shrink-0 text-right text-muted">{step >= SLIDER_STEPS ? "full window" : istDateTime(new Date(cutoff).toISOString())}</span>
        </label>
        {anyExpanded && (
          <Button size="sm" variant="ghost" onClick={() => setExpanded({ sender: false, receiver: false })}>Show top 8</Button>
        )}
        <Legend />
        <span className="num shrink-0 text-xs text-muted">in {inrShort(view.nodes.find((n) => n.role === "mule")?.amount)}</span>
      </div>
    </div>
  );
}

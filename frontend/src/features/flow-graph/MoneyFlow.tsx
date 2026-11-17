/**
 * Money-flow tab: senders on the left, the flagged account in the centre,
 * receivers on the right (dagre, left to right). Edge width is amount, label is
 * count, edge colour is exit speed. Hover highlights a path, click opens the
 * account drawer, and the time slider replays the window by first activity.
 */
import { useMemo, useState } from "react";
import { Background, Controls, MarkerType, MiniMap, ReactFlow, type Edge } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { useCase, useFlow } from "../../lib/queries";
import type { Flow } from "../../types/api";
import { ErrorState, SkeletonRows, Empty } from "../../components/ui/primitives";
import { ageDays, inrShort, istDateTime, minutes } from "../../lib/format";
import { exitColor } from "../../lib/meta";
import { isInternalAccount, useAccountDrawer } from "../../app/AccountDrawerContext";
import { AccountNode, type AccountFlowNode } from "./AccountNode";

const NODE_TYPES = { account: AccountNode };
const NODE_W = 200;
const NODE_H = 72;
const SLIDER_STEPS = 100;

function layout(flow: Flow): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 14, ranksep: 180 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of flow.nodes) g.setNode(n.id, { width: n.role === "mule" ? 240 : NODE_W, height: NODE_H });
  for (const e of flow.edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  const out = new Map<string, { x: number; y: number }>();
  for (const n of flow.nodes) {
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
      <span className="ml-2">exit speed:</span>
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1"><span className="h-0.5 w-4" style={{ background: color }} />{label}</span>
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

  const win = detail.data?.alert.window;
  const startMs = win ? new Date(win.start).getTime() : 0;
  const endMs = win ? new Date(win.end).getTime() : 0;
  const cutoff = startMs + ((endMs - startMs) * step) / SLIDER_STEPS;
  const positions = useMemo(() => (flow.data ? layout(flow.data) : new Map<string, { x: number; y: number }>()), [flow.data]);
  const maxAmount = useMemo(() => Math.max(1, ...(flow.data?.edges.map((e) => e.amount) ?? [1])), [flow.data]);

  const { nodes, edges } = useMemo(() => {
    if (!flow.data) return { nodes: [] as AccountFlowNode[], edges: [] as Edge[] };
    const mule = flow.data.nodes.find((n) => n.role === "mule");
    const visible = (ts: string | null | undefined) => !ts || step >= SLIDER_STEPS || new Date(ts).getTime() <= cutoff;
    const onPath = (id: string) => !hover || hover === id || id === mule?.id;
    const nodes: AccountFlowNode[] = flow.data.nodes.map((n) => ({
      id: n.id,
      type: "account",
      position: positions.get(n.id) ?? { x: 0, y: 0 },
      draggable: false,
      data: { flow: n, dimmed: !visible(n.first_ts) || !onPath(n.id), ageDays: n.role === "mule" ? ageDays(n.opened_at, startMs) : null, internal: isInternalAccount(n.ref) },
    }));
    const edges: Edge[] = flow.data.edges.map((e) => {
      const party = e.source === mule?.id ? e.target : e.source;
      const node = flow.data.nodes.find((n) => n.id === party);
      const dim = !visible(node?.first_ts) || (hover !== null && hover !== party && hover !== mule?.id);
      const color = e.source === mule?.id ? exitColor(e.exit_minutes) : "var(--c-role-sender)";
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: `${e.count}×${e.exit_minutes != null ? ` · ${minutes(e.exit_minutes)}` : ""}`,
        labelStyle: { fontSize: 10, fill: "var(--c-text-secondary)" },
        style: { stroke: color, strokeWidth: 1 + (e.amount / maxAmount) * 7, opacity: dim ? 0.12 : 0.85 },
        markerEnd: { type: MarkerType.ArrowClosed, color },
        animated: !dim && e.exit_minutes != null && e.exit_minutes < 30,
      };
    });
    return { nodes, edges };
  }, [flow.data, positions, hover, step, cutoff, maxAmount, startMs]);

  if (flow.isLoading) return <SkeletonRows rows={8} />;
  if (flow.isError) return <ErrorState error={flow.error} />;
  if (!flow.data || flow.data.nodes.length <= 1) return <Empty>No transactions in the alert window.</Empty>;

  return (
    <div className="flex h-full flex-col">
      <div className="h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          minZoom={0.2}
          proOptions={{ hideAttribution: true }}
          nodesConnectable={false}
          onNodeMouseEnter={(_, n) => setHover(n.id)}
          onNodeMouseLeave={() => setHover(null)}
          onNodeClick={(_, n) => {
            const f = (n as AccountFlowNode).data.flow;
            if (f.role === "mule" && detail.data) drawer.open(detail.data.account.id);
            else if (isInternalAccount(f.ref)) drawer.open(f.ref);
          }}
        >
          <Background color="var(--c-border)" gap={24} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={(n) => `var(--c-role-${(n as AccountFlowNode).data.flow.role})`} maskColor="rgba(11,15,26,0.7)" />
        </ReactFlow>
      </div>
      <div className="flex shrink-0 items-center gap-4 border-t border-line px-3 py-2">
        <label className="flex flex-1 items-center gap-3 text-xs text-secondary">
          Replay
          <input type="range" min={0} max={SLIDER_STEPS} value={step} onChange={(e) => setStep(Number(e.target.value))} className="flex-1 accent-[var(--c-accent)]" aria-label="Replay the alert window" />
          <span className="num w-36 text-right text-muted">{step >= SLIDER_STEPS ? "full window" : istDateTime(new Date(cutoff).toISOString())}</span>
        </label>
        <Legend />
        <span className="num text-xs text-muted">in {inrShort(flow.data.nodes.find((n) => n.role === "mule")?.amount)}</span>
      </div>
    </div>
  );
}

/**
 * Collapses the money-flow read model to the top senders and receivers by
 * amount, folding the rest of each side into one aggregate card ("30 other
 * senders"). The API already folds parties beyond its own top 24 / 12 into a
 * `group` node labelled "N more"; those are counted back into the aggregate so
 * the party count stays exact. Pure function; no rendering here.
 */
import type { Flow, FlowEdge, FlowNode } from "../../types/api";

export const TOP_PARTIES = 8;

export type Side = "sender" | "receiver";

export interface AggregateInfo {
  side: Side;
  parties: number;
}

export interface CollapsedFlow {
  nodes: FlowNode[];
  edges: FlowEdge[];
  aggregates: Map<string, AggregateInfo>;
}

const GROUP_LABEL = /^(\d+) more$/;

/** Number of parties a node stands for: 1, or N for an API "N more" group. */
function partiesIn(n: FlowNode): number {
  const m = n.sublabel === "group" ? GROUP_LABEL.exec(n.label ?? "") : null;
  return m ? Number(m[1]) : 1;
}

function earliest(values: (string | null | undefined)[]): string | null {
  const ts = values.filter((v): v is string => Boolean(v)).sort();
  return ts[0] ?? null;
}

function collapseSide(flow: Flow, side: Side, muleId: string): { nodes: FlowNode[]; edges: FlowEdge[]; aggregate: [string, AggregateInfo] | null } {
  const sideNodes = flow.nodes.filter((n) => n.role === side).sort((a, b) => b.amount - a.amount);
  // Real parties first; the API's own "N more" group always belongs to the tail.
  const parties = sideNodes.filter((n) => n.sublabel !== "group");
  const keep = parties.slice(0, TOP_PARTIES);
  const tail = [...parties.slice(TOP_PARTIES), ...sideNodes.filter((n) => n.sublabel === "group")];
  const keptIds = new Set(keep.map((n) => n.id));
  const sideEdges = flow.edges.filter((e) => (side === "sender" ? e.target === muleId : e.source === muleId));
  const edgeOf = (id: string) => sideEdges.find((e) => (side === "sender" ? e.source === id : e.target === id));
  const keptEdges = sideEdges.filter((e) => keptIds.has(side === "sender" ? e.source : e.target));

  const count = tail.reduce((t, n) => t + partiesIn(n), 0);
  // One leftover party is shown as itself; an aggregate of one helps nobody.
  if (tail.length === 0 || (tail.length === 1 && count === 1)) {
    return { nodes: sideNodes, edges: sideEdges, aggregate: null };
  }
  const id = `agg:${side}`;
  const amount = tail.reduce((t, n) => t + n.amount, 0);
  const tx = tail.reduce((t, n) => t + n.count, 0);
  const tailEdges = tail.map((n) => edgeOf(n.id)).filter((e): e is FlowEdge => Boolean(e));
  // Exit speed of the aggregate edge: that of its largest leftover flow.
  const biggest = [...tailEdges].sort((a, b) => b.amount - a.amount)[0];
  const node: FlowNode = {
    id,
    role: side,
    label: `${count} other ${side === "sender" ? "senders" : "receivers"}`,
    sublabel: "group",
    amount: Math.round(amount * 100) / 100,
    count: tx,
    first_ts: earliest(tail.map((n) => n.first_ts)),
  };
  const edge: FlowEdge = {
    id: `e-${id}`,
    source: side === "sender" ? id : muleId,
    target: side === "sender" ? muleId : id,
    amount: node.amount,
    count: tx,
    channel: null,
    exit_minutes: side === "receiver" ? (biggest?.exit_minutes ?? null) : null,
  };
  return { nodes: [...keep, node], edges: [...keptEdges, edge], aggregate: [id, { side, parties: count }] };
}

/** Top parties per side plus one aggregate card each, unless that side is expanded. */
export function collapseFlow(flow: Flow, expanded: Record<Side, boolean>): CollapsedFlow {
  const mule = flow.nodes.find((n) => n.role === "mule");
  if (!mule) return { nodes: flow.nodes, edges: flow.edges, aggregates: new Map() };
  const nodes: FlowNode[] = [mule];
  const edges: FlowEdge[] = [];
  const aggregates = new Map<string, AggregateInfo>();
  for (const side of ["sender", "receiver"] as const) {
    if (expanded[side]) {
      nodes.push(...flow.nodes.filter((n) => n.role === side));
      edges.push(...flow.edges.filter((e) => (side === "sender" ? e.target === mule.id : e.source === mule.id)));
      continue;
    }
    const part = collapseSide(flow, side, mule.id);
    nodes.push(...part.nodes);
    edges.push(...part.edges);
    if (part.aggregate) aggregates.set(...part.aggregate);
  }
  return { nodes, edges, aggregates };
}

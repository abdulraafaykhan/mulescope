/**
 * Custom React Flow node: an account card coloured by role (sender, mule,
 * receiver) with name, masked number or party type, amount, count and flags.
 * Memoised so pan and zoom stay smooth with ~40 nodes.
 */
import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Building2, Flag, User, Users } from "lucide-react";
import type { FlowNode } from "../../types/api";
import { inrShort } from "../../lib/format";

export interface AccountNodeData extends Record<string, unknown> {
  flow: FlowNode;
  dimmed: boolean;
  ageDays: number | null;
  internal: boolean;
}

export type AccountFlowNode = Node<AccountNodeData, "account">;

function AccountNodeView({ data }: NodeProps<AccountFlowNode>) {
  const { flow, dimmed, ageDays, internal } = data;
  const color = `var(--c-role-${flow.role})`;
  const isMule = flow.role === "mule";
  const Icon = flow.sublabel === "group" ? Users : internal || isMule ? Building2 : User;
  return (
    <div
      className="rounded-[8px] border bg-panel px-3 py-2 transition-opacity"
      style={{ width: isMule ? 230 : 190, borderColor: color, opacity: dimmed ? 0.25 : 1, boxShadow: isMule ? `0 0 0 3px color-mix(in srgb, ${color} 25%, transparent)` : undefined, cursor: internal || isMule ? "pointer" : "default" }}
    >
      {flow.role !== "sender" && <Handle type="target" position={Position.Left} style={{ background: color, border: 0 }} />}
      <div className="flex items-center gap-1.5">
        <Icon size={12} style={{ color }} aria-hidden />
        <span className={`truncate ${isMule ? "text-sm font-semibold" : "text-xs font-medium"} text-primary`}>{flow.label ?? "Unknown"}</span>
        {isMule && <Flag size={12} className="ml-auto shrink-0 text-role-mule" aria-label="Flagged account" />}
      </div>
      <div className="num mt-0.5 flex justify-between text-[11px] text-muted">
        <span className="truncate">{flow.sublabel ?? ""}</span>
        <span>×{flow.count}</span>
      </div>
      <div className="num mt-0.5 flex justify-between text-xs">
        <span style={{ color }}>{inrShort(flow.amount)}</span>
        {isMule && <span className="text-secondary">bal {inrShort(flow.balance ?? null)}</span>}
      </div>
      {isMule && ageDays != null && <div className="text-[11px] text-muted">account age {ageDays} d</div>}
      {flow.role !== "receiver" && <Handle type="source" position={Position.Right} style={{ background: color, border: 0 }} />}
    </div>
  );
}

export const AccountNode = memo(AccountNodeView);

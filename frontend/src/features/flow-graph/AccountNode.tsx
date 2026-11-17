/**
 * Custom React Flow node: an account card coloured by role (sender, mule,
 * receiver). Party cards are compact two-line cards (name and transfer count,
 * then amount and party type) sized so nine fit a column at 1440x900 without
 * zooming. The flagged account gets a larger card with its key facts. An
 * aggregate card ("30 other senders") expands that side when clicked.
 * Memoised so pan and zoom stay smooth.
 */
import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Building2, ChevronsUpDown, Flag, User, Users } from "lucide-react";
import type { FlowNode } from "../../types/api";
import { humanize, inrShort } from "../../lib/format";

export const PARTY_W = 200;
export const PARTY_H = 46;
export const MULE_W = 230;
export const MULE_H = 104;

export interface AccountNodeData extends Record<string, unknown> {
  flow: FlowNode;
  dimmed: boolean;
  ageDays: number | null;
  internal: boolean;
  aggregate: boolean;
}

export type AccountFlowNode = Node<AccountNodeData, "account">;

function MuleCard({ flow, ageDays }: { flow: FlowNode; ageDays: number | null }) {
  return (
    <>
      <div className="flex items-center gap-1.5">
        <Building2 size={14} className="shrink-0 text-role-mule" aria-hidden />
        <span className="truncate text-[15px] font-semibold text-primary">{flow.label ?? "Unknown"}</span>
        <Flag size={14} className="ml-auto shrink-0 text-role-mule" aria-label="Flagged account" />
      </div>
      <div className="num mt-0.5 text-[13px] text-secondary">{flow.sublabel}</div>
      <div className="num mt-1 flex justify-between text-[13px]">
        <span className="text-role-mule">in {inrShort(flow.amount)}</span>
        <span className="text-secondary">×{flow.count}</span>
      </div>
      <div className="num flex justify-between text-[12px] text-muted">
        <span>bal {inrShort(flow.balance ?? null)}</span>
        {ageDays != null && <span>age {ageDays} d</span>}
      </div>
    </>
  );
}

function PartyCard({ flow, internal, aggregate }: { flow: FlowNode; internal: boolean; aggregate: boolean }) {
  const Icon = aggregate || flow.sublabel === "group" ? Users : internal ? Building2 : User;
  const color = `var(--c-role-${flow.role})`;
  return (
    <>
      <div className="flex items-center gap-1.5">
        <Icon size={13} className="shrink-0" style={{ color }} aria-hidden />
        <span className="truncate text-[13px] font-medium text-primary">{flow.label ?? "Unknown"}</span>
        <span className="num ml-auto shrink-0 text-[12px] text-muted">×{flow.count}</span>
      </div>
      <div className="num flex items-center justify-between text-[12px]">
        <span style={{ color }}>{inrShort(flow.amount)}</span>
        {aggregate ? (
          <span className="flex items-center gap-0.5 text-secondary"><ChevronsUpDown size={11} aria-hidden />expand</span>
        ) : (
          <span className="truncate pl-2 text-muted">{humanize(flow.sublabel)}</span>
        )}
      </div>
    </>
  );
}

function AccountNodeView({ data }: NodeProps<AccountFlowNode>) {
  const { flow, dimmed, ageDays, internal, aggregate } = data;
  const color = `var(--c-role-${flow.role})`;
  const isMule = flow.role === "mule";
  const clickable = isMule || internal || aggregate;
  return (
    <div
      className={`rounded-[8px] border bg-panel transition-opacity ${isMule ? "px-3 py-2" : "px-2.5 py-1.5"} ${aggregate ? "border-dashed" : ""}`}
      style={{
        width: isMule ? MULE_W : PARTY_W,
        height: isMule ? MULE_H : PARTY_H,
        borderColor: color,
        borderWidth: isMule ? 2 : 1,
        opacity: dimmed ? 0.25 : 1,
        boxShadow: isMule ? `0 0 0 4px color-mix(in srgb, ${color} 22%, transparent)` : undefined,
        cursor: clickable ? "pointer" : "default",
      }}
      title={aggregate ? "Click to show every party on this side" : undefined}
    >
      {flow.role !== "sender" && <Handle type="target" position={Position.Left} style={{ background: color, border: 0 }} />}
      {isMule ? <MuleCard flow={flow} ageDays={ageDays} /> : <PartyCard flow={flow} internal={internal} aggregate={aggregate} />}
      {flow.role !== "receiver" && <Handle type="source" position={Position.Right} style={{ background: color, border: 0 }} />}
    </div>
  );
}

export const AccountNode = memo(AccountNodeView);

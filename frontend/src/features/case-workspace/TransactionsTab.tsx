/**
 * Transactions tab: virtualised ledger of the alert window (cursor-paged by
 * the API) with direction/channel/text filters and the evidence ids that cite
 * each row. The filters sit on one compact line; the column header lives
 * inside the scrolling table (sticky), so the rows get the rest of the height.
 * Columns shrink with the panel instead of scrolling sideways.
 */
import { useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import { useTransactions } from "../../lib/queries";
import { Button, Empty, ErrorState, SkeletonRows } from "../../components/ui/primitives";
import { inr, istDateTime, istDay, istTime } from "../../lib/format";
import { isInternalAccount, useAccountDrawer } from "../../app/AccountDrawerContext";
import { EvdChip } from "./EvdChip";
import { useEvidenceCtx } from "./EvidenceContext";

const ROW_H = 34;
const HEADER_H = 30;
const COLS = "grid grid-cols-[96px_14px_48px_minmax(0,1fr)_minmax(0,1.3fr)_100px_100px_92px] items-center gap-2 px-3";
const SELECT = "h-7 rounded-md border border-line bg-elevated px-2 text-xs text-primary";

export function TransactionsTab({ caseId }: { caseId: string }) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const page = useTransactions(caseId, cursor);
  const drawer = useAccountDrawer();
  const { highlighted } = useEvidenceCtx();
  const [direction, setDirection] = useState("");
  const [channel, setChannel] = useState("");
  const [text, setText] = useState("");
  const parentRef = useRef<HTMLDivElement>(null);

  const items = page.data?.items ?? [];
  const channels = useMemo(() => [...new Set(items.map((r) => r.channel))].sort(), [items]);
  const rows = useMemo(() => {
    const q = text.trim().toLowerCase();
    return items.filter((r) => (!direction || r.direction === direction) && (!channel || r.channel === channel) && (!q || `${r.cp_name ?? ""} ${r.remarks ?? ""}`.toLowerCase().includes(q)));
  }, [items, direction, channel, text]);

  // The sticky header sits above the rows inside the scroll element.
  const virtual = useVirtualizer({ count: rows.length, getScrollElement: () => parentRef.current, estimateSize: () => ROW_H, overscan: 12, scrollMargin: HEADER_H });

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-line px-3">
        <select aria-label="Direction" value={direction} onChange={(e) => setDirection(e.target.value)} className={SELECT}>
          <option value="">In and out</option>
          <option value="credit">Credits</option>
          <option value="debit">Debits</option>
        </select>
        <select aria-label="Channel" value={channel} onChange={(e) => setChannel(e.target.value)} className={SELECT}>
          <option value="">All channels</option>
          {channels.map((c) => <option key={c} value={c}>{c.toUpperCase().replace("_", " ")}</option>)}
        </select>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search counterparty or remark" aria-label="Search counterparty or remark" className={`${SELECT} w-0 max-w-64 min-w-24 flex-1 placeholder:text-muted`} />
        <span className="num ml-auto text-xs whitespace-nowrap text-muted" title="Entries shown / entries on this page">{rows.length} / {items.length}</span>
        <Button size="sm" variant="ghost" disabled={cursors.length <= 1} onClick={() => setCursors((c) => c.slice(0, -1))} aria-label="Newer page"><ChevronLeft size={14} /></Button>
        <Button size="sm" variant="ghost" disabled={!page.data?.next_cursor} onClick={() => page.data?.next_cursor && setCursors((c) => [...c, page.data.next_cursor])} aria-label="Older page"><ChevronRight size={14} /></Button>
      </div>
      {page.isLoading && <SkeletonRows rows={10} />}
      {page.isError && <ErrorState error={page.error} />}
      {page.data && rows.length === 0 && <Empty>No entries match.</Empty>}
      <div ref={parentRef} className="min-h-0 flex-1 overflow-y-auto">
        {rows.length > 0 && (
          <div role="row" className={`${COLS} sticky top-0 z-10 border-b border-line bg-elevated text-xs text-secondary`} style={{ height: HEADER_H }}>
            <span>Time (IST)</span><span /><span>Channel</span><span>Counterparty</span><span>Remarks (untrusted)</span><span className="text-right">Amount</span><span className="text-right">Balance after</span><span>Cited by</span>
          </div>
        )}
        <div style={{ height: virtual.getTotalSize(), position: "relative" }}>
          {virtual.getVirtualItems().map((v) => {
            const r = rows[v.index];
            const credit = r.direction === "credit";
            const cited = highlighted !== null && (r.evidence_ids ?? []).includes(highlighted);
            return (
              <div key={r.id} className={`${COLS} absolute right-0 left-0 border-b border-line/50 text-xs ${cited ? "bg-accent/10" : ""}`} style={{ top: v.start - HEADER_H, height: ROW_H }}>
                <span className="num truncate text-muted" title={istDateTime(r.ts)}>{istDay(r.ts)} {istTime(r.ts).slice(0, 5)}</span>
                {credit ? <ArrowDownLeft size={12} className="text-role-sender" aria-label="credit" /> : <ArrowUpRight size={12} className="text-role-receiver" aria-label="debit" />}
                <span className="num truncate text-secondary uppercase">{r.channel.replace("_", " ")}</span>
                <span className="truncate">
                  {isInternalAccount(r.cp_ref) ? <button type="button" className="text-primary hover:underline" onClick={() => drawer.open(r.cp_ref as string)}>{r.cp_name}</button> : <span className="text-primary" title={r.cp_name ?? undefined}>{r.cp_name ?? "—"}</span>}
                </span>
                <span className="num truncate text-muted" title={r.remarks ?? ""}>{r.remarks}</span>
                <span className="num text-right" style={{ color: credit ? "var(--c-role-sender)" : "var(--c-role-receiver)" }}>{credit ? "+" : "−"}{inr(r.amount)}</span>
                <span className="num text-right text-secondary">{inr(r.balance_after)}</span>
                <span className="flex items-center gap-1 whitespace-nowrap">
                  {(r.evidence_ids ?? []).slice(0, 1).map((id) => <EvdChip key={id} id={id} />)}
                  {(r.evidence_ids ?? []).length > 1 && <span className="text-muted">+{(r.evidence_ids ?? []).length - 1}</span>}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

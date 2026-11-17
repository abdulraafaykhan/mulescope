/**
 * Audit log of one case: time, actor (in the actor's colour), event, entity
 * and an expandable payload, with the hash-chain verification badge and a
 * JSON export. Reads `GET /audit?case_id=` and `GET /cases/{id}/audit/verify`.
 */
import { Fragment, useEffect, useMemo, useState } from "react";
import { Download, Link2, Link2Off } from "lucide-react";
import { useAudit, useChainVerify } from "../../lib/queries";
import { Button, Empty, ErrorState, SkeletonRows } from "../../components/ui/primitives";
import { Chip } from "../../components/ui/chips";
import { istDateTime, shortHash } from "../../lib/format";
import { actorColor } from "../../lib/meta";

export function AuditLog({ caseId, runActive }: { caseId: string; runActive: boolean }) {
  const audit = useAudit(caseId);
  const verify = useChainVerify(caseId);
  const [actor, setActor] = useState("");
  const [text, setText] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  // While a run is active the chain grows; keep both views fresh.
  const { refetch: refetchAudit } = audit;
  const { refetch: refetchVerify } = verify;
  useEffect(() => {
    if (!runActive) return;
    const t = window.setInterval(() => {
      void refetchAudit();
      void refetchVerify();
    }, 4000);
    return () => window.clearInterval(t);
  }, [runActive, refetchAudit, refetchVerify]);

  const rows = useMemo(() => {
    const q = text.trim().toLowerCase();
    return (audit.data ?? []).filter((r) => (!actor || r.actor.type === actor) && (!q || `${r.event} ${r.actor.id} ${r.entity.id}`.toLowerCase().includes(q)));
  }, [audit.data, actor, text]);

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(audit.data ?? [], null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${caseId}-audit.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const v = verify.data;
  const select = "h-7 rounded-md border border-line bg-elevated px-2 text-xs text-primary";
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-1.5">
        {v && (
          <Chip color={v.valid ? "var(--c-risk-low)" : "var(--c-risk-critical)"} icon={v.valid ? <Link2 size={12} aria-hidden /> : <Link2Off size={12} aria-hidden />} title={v.valid ? `head ${v.head ?? ""}` : `broken at ${v.broken_at ?? ""}`}>
            {v.valid ? `Hash chain valid · ${v.records} records` : `Chain broken at ${v.broken_at}`}
          </Chip>
        )}
        <select aria-label="Actor type" value={actor} onChange={(e) => setActor(e.target.value)} className={select}>
          <option value="">All actors</option>
          <option value="system">System</option>
          <option value="agent">Agent</option>
          <option value="analyst">Analyst</option>
        </select>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Filter events" aria-label="Filter events" className={`${select} w-48 placeholder:text-muted`} />
        <Button size="sm" className="ml-auto" onClick={exportJson}><Download size={12} aria-hidden /> Export JSON</Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {audit.isLoading && <SkeletonRows rows={6} />}
        {audit.isError && <ErrorState error={audit.error} />}
        {audit.data && rows.length === 0 && <Empty>No audit events yet.</Empty>}
        <table className="w-full text-xs">
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <tr onClick={() => setOpen(open === r.id ? null : r.id)} className="cursor-pointer border-b border-line/50 hover:bg-elevated">
                  <td className="num w-40 px-3 py-1 text-muted">{istDateTime(r.ts)}</td>
                  <td className="w-44 px-2 py-1">
                    <span className="flex items-center gap-1.5" style={{ color: actorColor(r.actor.type, r.actor.id) }}>
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: actorColor(r.actor.type, r.actor.id) }} aria-hidden />
                      {r.actor.type} · {r.actor.id}
                    </span>
                  </td>
                  <td className="num px-2 py-1 text-primary">{r.event}</td>
                  <td className="num px-2 py-1 text-secondary">{r.entity.type} {r.entity.id}</td>
                  <td className="num w-32 px-3 py-1 text-right text-muted" title={r.hash}>{shortHash(r.hash)}</td>
                </tr>
                {open === r.id && (
                  <tr className="bg-app">
                    <td colSpan={5} className="px-3 py-2">
                      <pre className="num max-h-40 overflow-auto text-[11px] text-secondary">{JSON.stringify(r.payload, null, 2)}</pre>
                      <div className="num mt-1 text-[11px] text-muted">prev {r.prev_hash} → {r.hash}</div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

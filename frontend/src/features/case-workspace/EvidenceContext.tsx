/**
 * Case-scoped evidence context: the evidence map (for EVD chip hover cards),
 * the id of the run that ledger belongs to, and the highlighted evidence id,
 * so clicking an item highlights everywhere it is cited (report, actions,
 * transactions) and a chip click jumps to it.
 */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Evidence } from "../../types/api";

interface Ctx {
  byId: Map<string, Evidence>;
  /** Run whose evidence ledger `byId` holds (the case's latest run). */
  runId: string | null;
  highlighted: string | null;
  highlight: (id: string | null) => void;
  /** Highlight and scroll the evidence list to the item. */
  jumpTo: (id: string) => void;
}

const EvidenceCtx = createContext<Ctx>({ byId: new Map(), runId: null, highlighted: null, highlight: () => undefined, jumpTo: () => undefined });

export function EvidenceProvider({ evidence, runId, children }: { evidence: Evidence[]; runId: string | null; children: ReactNode }) {
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const value = useMemo<Ctx>(() => {
    const byId = new Map(evidence.map((e) => [e.id, e]));
    return {
      byId,
      runId,
      highlighted,
      highlight: setHighlighted,
      jumpTo: (id: string) => {
        setHighlighted(id);
        document.getElementById(`evd-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      },
    };
  }, [evidence, runId, highlighted]);
  return <EvidenceCtx.Provider value={value}>{children}</EvidenceCtx.Provider>;
}

export function useEvidenceCtx(): Ctx {
  return useContext(EvidenceCtx);
}

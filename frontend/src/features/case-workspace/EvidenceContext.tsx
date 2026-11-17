/**
 * Case-scoped evidence context: the evidence map (for EVD chip hover cards)
 * and the highlighted evidence id, so clicking an item highlights everywhere
 * it is cited (report, actions, transactions) and a chip click jumps to it.
 */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Evidence } from "../../types/api";

interface Ctx {
  byId: Map<string, Evidence>;
  highlighted: string | null;
  highlight: (id: string | null) => void;
  /** Highlight and scroll the evidence list to the item. */
  jumpTo: (id: string) => void;
}

const EvidenceCtx = createContext<Ctx>({ byId: new Map(), highlighted: null, highlight: () => undefined, jumpTo: () => undefined });

export function EvidenceProvider({ evidence, children }: { evidence: Evidence[]; children: ReactNode }) {
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const value = useMemo<Ctx>(() => {
    const byId = new Map(evidence.map((e) => [e.id, e]));
    return {
      byId,
      highlighted,
      highlight: setHighlighted,
      jumpTo: (id: string) => {
        setHighlighted(id);
        document.getElementById(`evd-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      },
    };
  }, [evidence, highlighted]);
  return <EvidenceCtx.Provider value={value}>{children}</EvidenceCtx.Provider>;
}

export function useEvidenceCtx(): Ctx {
  return useContext(EvidenceCtx);
}

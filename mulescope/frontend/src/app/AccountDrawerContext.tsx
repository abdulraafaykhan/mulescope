/**
 * App-wide account drawer: any account card, graph node or table cell can call
 * `open(accountId)`. The drawer itself lives in features/account.
 */
import { createContext, lazy, Suspense, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

// Lazy so Recharts stays out of the first-load bundle of the queue.
const AccountDrawer = lazy(() => import("../features/account/AccountDrawer").then((m) => ({ default: m.AccountDrawer })));

interface Ctx {
  open: (accountId: string) => void;
}

const AccountDrawerContext = createContext<Ctx>({ open: () => undefined });

export function AccountDrawerProvider({ children }: { children: ReactNode }) {
  const [accountId, setAccountId] = useState<string | null>(null);
  const close = useCallback(() => setAccountId(null), []);
  const value = useMemo(() => ({ open: (id: string) => setAccountId(id) }), []);
  return (
    <AccountDrawerContext.Provider value={value}>
      {children}
      {accountId && (
        <Suspense fallback={null}>
          <AccountDrawer accountId={accountId} onClose={close} />
        </Suspense>
      )}
    </AccountDrawerContext.Provider>
  );
}

export function useAccountDrawer(): Ctx {
  return useContext(AccountDrawerContext);
}

/** Internal accounts have `ACC-` ids; external counterparties cannot be opened. */
export function isInternalAccount(ref: string | null | undefined): ref is string {
  return Boolean(ref && ref.startsWith("ACC-"));
}

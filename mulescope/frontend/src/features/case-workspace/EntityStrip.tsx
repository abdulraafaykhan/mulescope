/**
 * Always-visible entity strip: Senders -> Mule account -> Receivers, coloured
 * by role, so the analyst sees who paid, which account is flagged and where
 * the money went within two seconds of opening the case.
 */
import type { ReactNode } from "react";
import { ArrowRight, Building2, ShieldAlert, User, Users } from "lucide-react";
import type { Account, Customer, EntityStrip as Strip, PartyTop } from "../../types/api";
import { ageDays, humanize, inrShort, int } from "../../lib/format";
import { isInternalAccount, useAccountDrawer } from "../../app/AccountDrawerContext";

const WINDOW_DAYS = 14;
const MONTH_DAYS = 30;

function Card({ role, title, icon, children }: { role: "sender" | "mule" | "receiver"; title: string; icon: ReactNode; children: ReactNode }) {
  const color = `var(--c-role-${role})`;
  return (
    <section className="min-w-0 flex-1 rounded-[8px] border bg-panel p-3" style={{ borderColor: `color-mix(in srgb, ${color} 45%, var(--c-border))`, boxShadow: `inset 3px 0 0 ${color}` }} aria-label={title}>
      <header className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase" style={{ color }}>
        {icon}
        {title}
      </header>
      {children}
    </section>
  );
}

function TopList({ items }: { items: PartyTop[] }) {
  const drawer = useAccountDrawer();
  return (
    <ul className="mt-2 space-y-1">
      {items.map((p) => {
        const internal = isInternalAccount(p.ref);
        return (
          <li key={p.ref} className="flex items-center justify-between gap-2 text-xs">
            <span className="flex min-w-0 items-center gap-1.5">
              {internal ? <Building2 size={11} className="shrink-0 text-muted" aria-label="Account at our bank" /> : <User size={11} className="shrink-0 text-muted" aria-label="External party" />}
              {internal ? (
                <button type="button" className="truncate text-primary hover:underline" onClick={() => drawer.open(p.ref)}>{p.name}</button>
              ) : (
                <span className="truncate text-primary">{p.name}</span>
              )}
              <span className="shrink-0 text-muted">×{p.count}</span>
            </span>
            <span className="num shrink-0 text-secondary">{inrShort(p.amount)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="num text-sm font-semibold" style={{ color: tone }}>{value}</div>
    </div>
  );
}

export function EntityStrip({ strip, customer, account, windowStart }: { strip: Strip; customer: Customer; account: Account; windowStart: string }) {
  const drawer = useAccountDrawer();
  const m = strip.mule;
  const monthly = (m.window_inflow * MONTH_DAYS) / WINDOW_DAYS;
  const multiple = m.declared_monthly_turnover ? monthly / m.declared_monthly_turnover : null;
  // Age at the start of the alert window, as the policy measures it.
  const age = ageDays(m.opened_at, new Date(windowStart).getTime());
  const flags: string[] = [];
  if (multiple != null && multiple >= 10) flags.push(`${multiple.toFixed(0)}× declared turnover`);
  if (age != null && age < 180) flags.push("new account");
  if (m.kyc_status && m.kyc_status !== "verified") flags.push(`KYC ${m.kyc_status}`);

  return (
    <div className="flex items-stretch gap-2">
      <Card role="sender" title={`Senders · ${int(strip.senders.count)}`} icon={<Users size={13} aria-hidden />}>
        <Stat label="Total in" value={inrShort(strip.senders.total)} />
        <TopList items={strip.senders.top} />
      </Card>
      <ArrowRight size={16} className="self-center text-muted" aria-hidden />
      <Card role="mule" title="Flagged account" icon={<ShieldAlert size={13} aria-hidden />}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <button type="button" onClick={() => drawer.open(account.id)} className="truncate text-left text-base font-semibold hover:underline">{m.name}</button>
            <div className="num text-xs text-secondary">{m.account_masked} · {account.type} · {account.branch}</div>
            <div className="text-xs text-muted">{humanize(m.occupation)} · {customer.kyc.city} · risk {customer.risk_rating}</div>
          </div>
          <div className="flex flex-wrap justify-end gap-1">
            {flags.map((f) => (
              <span key={f} className="rounded border border-role-mule/40 px-1.5 py-0.5 text-[11px] text-role-mule">⚑ {f}</span>
            ))}
          </div>
        </div>
        <div className="mt-2 grid grid-cols-4 gap-2">
          <Stat label="Declared turnover / mo" value={inrShort(m.declared_monthly_turnover)} />
          <Stat label="Actual / mo (window)" value={inrShort(monthly)} tone={multiple != null && multiple >= 10 ? "var(--c-risk-critical)" : undefined} />
          <Stat label="Account age" value={age == null ? "—" : `${age} d`} />
          <Stat label="Balance" value={inrShort(m.balance)} />
        </div>
      </Card>
      <ArrowRight size={16} className="self-center text-muted" aria-hidden />
      <Card role="receiver" title={`Receivers · ${int(strip.receivers.count)}`} icon={<Users size={13} aria-hidden />}>
        <div className="flex items-start justify-between gap-2">
          <Stat label="Total out" value={inrShort(strip.receivers.total)} />
          <div className="flex flex-wrap justify-end gap-1">
            {strip.receivers.channels.map((ch) => (
              <span key={ch} className="num rounded bg-elevated px-1.5 py-0.5 text-[11px] text-secondary uppercase">{ch.replace("_", " ")}</span>
            ))}
          </div>
        </div>
        <TopList items={strip.receivers.top} />
      </Card>
    </div>
  );
}

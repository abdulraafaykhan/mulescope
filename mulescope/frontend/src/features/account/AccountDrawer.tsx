/**
 * Account drawer: KYC block, account facts, balance sparkline, 90-day baseline
 * vs window, complaints, recent transactions and other cases on the account.
 * Account numbers and PAN arrive masked from the API and stay masked.
 */
import { Link } from "react-router";
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { useAccountSummary } from "../../lib/queries";
import { Drawer } from "../../components/ui/overlays";
import { ErrorState, Fact, Panel, SkeletonRows } from "../../components/ui/primitives";
import { CaseStatusChip } from "../../components/ui/chips";
import { humanize, inr, inrShort, istDate, istDateTime } from "../../lib/format";

function Baseline({ label, prior, current }: { label: string; prior: number; current: number }) {
  const ratio = prior > 0 ? current / prior : null;
  return (
    <div className="rounded-md bg-elevated p-2">
      <div className="text-[11px] text-muted">{label} / week</div>
      <div className="num text-sm">{inrShort(current)}</div>
      <div className="num text-[11px] text-muted">
        prior 90 d {inrShort(prior)}
        {ratio != null && <span style={{ color: ratio >= 3 ? "var(--c-risk-critical)" : undefined }}> · {ratio.toFixed(1)}×</span>}
      </div>
    </div>
  );
}

export function AccountDrawer({ accountId, onClose }: { accountId: string | null; onClose: () => void }) {
  const q = useAccountSummary(accountId);
  const s = q.data;
  return (
    <Drawer open={Boolean(accountId)} onClose={onClose} title={s ? `${s.account.holder_name} · ${s.account.account_no_masked}` : "Account"}>
      {q.isLoading && <SkeletonRows rows={10} />}
      {q.isError && <ErrorState error={q.error} />}
      {s && (
        <div className="space-y-3 p-4">
          <div className="grid grid-cols-2 gap-3">
            <Panel title="KYC" bodyClass="p-3">
              <Fact label="Name">{s.customer.kyc.name}</Fact>
              <Fact label="Occupation">{humanize(s.customer.kyc.occupation)}</Fact>
              <Fact label="City">{s.customer.kyc.city}</Fact>
              <Fact label="Declared income / yr" mono>{inrShort(s.customer.kyc.declared_income)}</Fact>
              <Fact label="PAN" mono>{s.customer.kyc.pan_masked}</Fact>
              <Fact label="KYC status">{s.customer.kyc.kyc_status}</Fact>
              <Fact label="KYC refreshed">{istDate(s.customer.kyc.kyc_refreshed_at)}</Fact>
              <Fact label="Risk rating">{s.customer.risk_rating}</Fact>
            </Panel>
            <Panel title="Account" bodyClass="p-3">
              <Fact label="Id" mono>{s.account.id}</Fact>
              <Fact label="Number" mono>{s.account.account_no_masked}</Fact>
              <Fact label="Type">{s.account.type}</Fact>
              <Fact label="Status">{s.account.status}</Fact>
              <Fact label="IFSC" mono>{s.account.ifsc}</Fact>
              <Fact label="VPA" mono>{s.account.vpa ?? "—"}</Fact>
              <Fact label="Opened">{istDate(s.account.opened_at)}</Fact>
              <Fact label="Declared turnover / mo" mono>{inrShort(s.account.declared_monthly_turnover)}</Fact>
              <Fact label="Balance" mono>{inr(s.account.balance)}</Fact>
            </Panel>
          </div>

          <Panel title="Balance (last 104 days)" bodyClass="h-28 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={s.balance_sparkline} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
                <YAxis hide domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "var(--c-bg-elevated)", border: "1px solid var(--c-border)", borderRadius: 8, fontSize: 12 }} formatter={(v) => [inr(Number(v)), "Balance"]} labelFormatter={(_, p) => String(p[0]?.payload?.date ?? "")} />
                <Area dataKey="balance" type="stepAfter" stroke="var(--c-accent)" fill="var(--c-accent)" fillOpacity={0.15} strokeWidth={1.5} />
              </AreaChart>
            </ResponsiveContainer>
          </Panel>

          <div className="grid grid-cols-2 gap-2">
            <Baseline label="Inflow" prior={s.baseline.prior_weekly_inflow} current={s.baseline.window_weekly_inflow} />
            <Baseline label="Outflow" prior={s.baseline.prior_weekly_outflow} current={s.baseline.window_weekly_outflow} />
          </div>

          <Panel title={`Complaints (${s.complaints.length})`} bodyClass="p-3">
            {s.complaints.length === 0 && <p className="text-xs text-muted">No fraud complaints name this account.</p>}
            {s.complaints.map((c) => (
              <div key={c.id} className="flex justify-between border-b border-line/50 py-1 text-xs last:border-0">
                <span className="num text-secondary">{c.id} · {istDate(c.reported_at)} · {c.status}</span>
                <span className="num text-risk-critical">{inr(c.amount)}</span>
              </div>
            ))}
          </Panel>

          <Panel title="Cases on this account" bodyClass="p-3">
            {s.cases.length === 0 && <p className="text-xs text-muted">No cases.</p>}
            {s.cases.map((c) => (
              <Link key={c.case_id} to={`/cases/${c.case_id}`} onClick={onClose} className="flex items-center justify-between py-1 text-xs hover:underline">
                <span className="num text-accent">{c.case_id}</span>
                <span className="flex items-center gap-2"><span className="num text-muted">score {c.score ?? "—"}</span><CaseStatusChip value={c.status} /></span>
              </Link>
            ))}
          </Panel>

          <Panel title="Recent transactions" bodyClass="py-1">
            {s.recent_transactions.map((r) => (
              <div key={r.id} className="grid grid-cols-[120px_16px_1fr_110px] items-center gap-2 px-3 py-1 text-xs">
                <span className="num text-muted">{istDateTime(r.ts)}</span>
                {r.direction === "credit" ? <ArrowDownLeft size={12} className="text-role-sender" aria-label="credit" /> : <ArrowUpRight size={12} className="text-role-receiver" aria-label="debit" />}
                <span className="truncate text-secondary">{r.cp_name ?? "—"} <span className="num text-muted uppercase">{r.channel.replace("_", " ")}</span></span>
                <span className="num text-right">{inr(r.amount)}</span>
              </div>
            ))}
          </Panel>
        </div>
      )}
    </Drawer>
  );
}

/**
 * Formatters (section 9.6): INR with Indian grouping, IST date/time, relative
 * time, account masking and labels. Components never format inline.
 */
import type { Disposition } from "../types/api";

const inrFull = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inrWhole = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const intIn = new Intl.NumberFormat("en-IN");
const IST = "Asia/Kolkata";
const dateTimeIst = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
const dateIst = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short", year: "numeric" });
const timeIst = new Intl.DateTimeFormat("en-IN", { timeZone: IST, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const dayIst = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short" });

/** `123456.5` -> `₹1,23,456.50`. */
export function inr(value: number | null | undefined): string {
  return value == null ? "—" : inrFull.format(value);
}

/** `123456.5` -> `₹1,23,457` (cards and KPIs where paise are noise). */
export function inrShort(value: number | null | undefined): string {
  return value == null ? "—" : inrWhole.format(value);
}

/** Compact INR in lakh / crore, for chart axes: `₹12.4L`, `₹1.2Cr`. */
export function inrCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(1)}Cr`;
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(1)}L`;
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(0)}k`;
  return `₹${value.toFixed(0)}`;
}

export function int(value: number | null | undefined): string {
  return value == null ? "—" : intIn.format(value);
}

export function pct(value: number | null | undefined, digits = 0): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

/** ISO UTC -> `14 Oct, 21:05 IST`. */
export function istDateTime(iso: string | null | undefined): string {
  return iso ? `${dateTimeIst.format(new Date(iso))} IST` : "—";
}

export function istDate(iso: string | null | undefined): string {
  return iso ? dateIst.format(new Date(iso)) : "—";
}

export function istTime(iso: string | null | undefined): string {
  return iso ? timeIst.format(new Date(iso)) : "—";
}

export function istDay(iso: string): string {
  return dayIst.format(new Date(iso));
}

/** Signed human duration until `iso`: `in 2d 4h`, `3h ago`. */
export function relative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - now;
  const abs = Math.abs(diff);
  const d = Math.floor(abs / 86_400_000);
  const h = Math.floor((abs % 86_400_000) / 3_600_000);
  const m = Math.floor((abs % 3_600_000) / 60_000);
  const text = d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

/** Days between an ISO date and now (account age). */
export function ageDays(iso: string | null | undefined, now: number = Date.now()): number | null {
  return iso ? Math.max(0, Math.floor((now - new Date(iso).getTime()) / 86_400_000)) : null;
}

/** Masks anything that looks like an account number: keeps the last 4 digits. */
export function maskAccount(value: string | null | undefined): string {
  if (!value) return "—";
  if (value.startsWith("XXXX")) return value;
  const digits = value.replace(/\D/g, "");
  return digits.length >= 4 ? `XXXX${digits.slice(-4)}` : value;
}

export function minutes(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value < 60) return `${value.toFixed(0)} min`;
  if (value < 1440) return `${(value / 60).toFixed(1)} h`;
  return `${(value / 1440).toFixed(1)} d`;
}

export function ms(value: number | null | undefined): string {
  if (value == null) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}

/** `request_customer_clarification` -> `Request customer clarification`. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const s = value.replace(/[._]/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  close: "Close",
  escalate: "Escalate",
  str_draft: "STR draft",
};

export function shortHash(hash: string | null | undefined): string {
  return hash ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : "—";
}

/**
 * Small UI primitives (hand-written in the shadcn style: Tailwind classes, no
 * runtime theme). Panel, Button, Skeleton, empty and error states.
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, Inbox } from "lucide-react";

export function Panel({ title, actions, children, className = "", bodyClass = "" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`rounded-[8px] border border-line bg-panel ${className}`}>
      {title !== undefined && (
        <header className="flex h-9 items-center justify-between border-b border-line px-3">
          <h2 className="text-xs font-semibold tracking-wide text-secondary uppercase">{title}</h2>
          {actions}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-white hover:brightness-110 border-transparent",
  secondary: "bg-elevated text-primary hover:bg-line border-line",
  ghost: "bg-transparent text-secondary hover:bg-elevated hover:text-primary border-transparent",
  danger: "bg-transparent text-risk-critical border-risk-critical/50 hover:bg-risk-critical/10",
  success: "bg-transparent text-risk-low border-risk-low/50 hover:bg-risk-low/10",
};

export function Button({ variant = "secondary", size = "md", className = "", children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  const sz = size === "sm" ? "h-7 px-2 text-xs gap-1" : "h-8 px-3 text-sm gap-1.5";
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-md border font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${sz} ${VARIANT[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-elevated ${className}`} />;
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-5 w-full" />
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted">
      <Inbox size={18} aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="flex items-start gap-2 p-4 text-sm text-risk-critical">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

/** Label/value row used in fact lists. */
export function Fact({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className={`text-right text-primary ${mono ? "num" : ""}`}>{children}</span>
    </div>
  );
}

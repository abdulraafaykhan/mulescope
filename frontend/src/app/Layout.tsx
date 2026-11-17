/**
 * App frame: top bar with navigation, LLM mode and API health. Content below
 * fills the viewport; each page manages its own scrolling.
 */
import { NavLink, Outlet } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Activity, FlaskConical, ListChecks, ScanSearch } from "lucide-react";
import { fetchHealth } from "../lib/api";
import { usePublicConfig } from "../lib/queries";
import { Chip } from "../components/ui/chips";

function navClass({ isActive }: { isActive: boolean }) {
  return `flex h-8 items-center gap-1.5 rounded-md px-3 text-sm ${isActive ? "bg-elevated text-primary" : "text-secondary hover:text-primary"}`;
}

export function Layout() {
  const config = usePublicConfig();
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 30_000, retry: false });
  const healthy = health.data?.status === "ok";
  const mode = config.data?.llm_mode;
  return (
    <div className="flex h-full flex-col">
      <header className="no-print flex h-12 shrink-0 items-center justify-between border-b border-line bg-panel px-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 font-semibold">
            <ScanSearch size={18} className="text-accent" aria-hidden />
            <span>MuleScope</span>
            <span className="text-xs font-normal text-muted">AML triage · rapid pass-through</span>
          </div>
          <nav className="flex items-center gap-1" aria-label="Main">
            <NavLink to="/" end className={navClass}>
              <ListChecks size={14} aria-hidden /> Alert queue
            </NavLink>
            <NavLink to="/evals" className={navClass}>
              <FlaskConical size={14} aria-hidden /> Evals
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {mode && (
            <Chip color={mode === "live" ? "var(--c-agent-flow)" : "var(--c-risk-medium)"} title="LLM mode (LLM_MODE)">
              LLM {mode}
            </Chip>
          )}
          {config.data && <span className="num text-muted">graph v{config.data.graph_version}</span>}
          <span className="flex items-center gap-1.5 text-secondary" title={health.data ? `api ${health.data.status}, db ${health.data.db}` : "API unreachable"}>
            <Activity size={14} style={{ color: healthy ? "var(--c-risk-low)" : "var(--c-risk-critical)" }} aria-hidden />
            {healthy ? "API ok" : health.isLoading ? "API…" : "API down"}
          </span>
          <span className="text-muted">analyst-1</span>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}

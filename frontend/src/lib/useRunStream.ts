/**
 * SSE hook for one run (`GET /api/v1/runs/{run_id}/stream`).
 *
 * The stream has no heartbeat and its history lives in API memory, so the hook
 * assumes it can drop at any time:
 *   - on error it closes the EventSource, refetches the persisted run state
 *     (case detail + node_executions diagnostics) and reconnects with backoff;
 *   - each (re)connect clears the live event list, because the server replays
 *     the run's history from the start;
 *   - after `run_completed` / `run_failed` it stops and refetches the case.
 * The Agents stepper merges these live events over the persisted diagnostics,
 * so it stays correct even when history was lost in an API restart.
 */
import { useEffect, useRef, useState } from "react";
import { API_V1 } from "./api";
import { useInvalidateCase } from "./queries";
import type { RunEvent } from "../types/api";

export type StreamState = "idle" | "connecting" | "open" | "reconnecting" | "closed";

const EVENT_TYPES = ["node", "interrupt", "run_completed", "run_failed"] as const;
const MAX_BACKOFF_MS = 10_000;

export function useRunStream(caseId: string, runId: string | null | undefined, active: boolean) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [state, setState] = useState<StreamState>("idle");
  const invalidate = useInvalidateCase();
  const invalidateRef = useRef(invalidate);
  invalidateRef.current = invalidate;

  useEffect(() => {
    if (!runId || !active) {
      setState(runId ? "closed" : "idle");
      return;
    }
    let es: EventSource | null = null;
    let timer: number | undefined;
    let attempt = 0;
    let finished = false;

    const connect = () => {
      setState(attempt === 0 ? "connecting" : "reconnecting");
      setEvents([]);
      es = new EventSource(`${API_V1}/runs/${runId}/stream`);
      es.onopen = () => {
        attempt = 0;
        setState("open");
      };
      for (const type of EVENT_TYPES) {
        es.addEventListener(type, (msg: MessageEvent<string>) => {
          const event = JSON.parse(msg.data) as RunEvent;
          setEvents((prev) => [...prev, event]);
          if (event.type === "interrupt") invalidateRef.current(caseId);
          if (event.type === "node" && (event.status === "done" || event.status === "fallback") && ["aggregate_evidence", "score_and_policy", "plan_actions", "critic", "execute_actions"].includes(event.node)) {
            invalidateRef.current(caseId);
          }
          if (event.type === "run_completed" || event.type === "run_failed") {
            finished = true;
            es?.close();
            setState("closed");
            invalidateRef.current(caseId);
          }
        });
      }
      es.onerror = () => {
        es?.close();
        if (finished) return;
        // Dropped stream: refetch persisted state, then reconnect with backoff.
        invalidateRef.current(caseId);
        const delay = Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
        attempt += 1;
        setState("reconnecting");
        timer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      finished = true;
      if (timer) window.clearTimeout(timer);
      es?.close();
    };
  }, [caseId, runId, active]);

  return { events, state };
}

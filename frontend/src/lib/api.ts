/**
 * Thin fetch client for the MuleScope API. Throws `ApiError` with the backend
 * error envelope (`{error: {code, message, detail}}`) so panels can show it.
 */
import type { ApiErrorEnvelope } from "../types/api";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8742";
export const API_V1 = `${API_URL}/api/v1`;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function isEnvelope(body: unknown): body is ApiErrorEnvelope {
  return typeof body === "object" && body !== null && "error" in body;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_V1}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError(0, "network", `Cannot reach the API at ${API_URL}. Is \`uv run dev\` running?`);
  }
  const text = await res.text();
  const body: unknown = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (isEnvelope(body)) throw new ApiError(res.status, body.error.code, body.error.message);
    throw new ApiError(res.status, "http", `${res.status} ${res.statusText}`);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};

/** Fetch the root health route (outside /api/v1). */
export async function fetchHealth(): Promise<{ status: string; db: string }> {
  const res = await fetch(`${API_URL}/health`);
  return (await res.json()) as { status: string; db: string };
}

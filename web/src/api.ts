import type { Demo } from "./types";

export interface CreateSessionBody {
  mode: "demo" | "live";
  demo_id?: string;
  jd_text?: string;
  evidence_text?: string;
  evidence_format?: "yaml" | "markdown";
  round_text?: string;
  research_text?: string;
  provider?: "gemini" | "azure";
  gemini_api_key?: string;
  azure_api_key?: string;
  azure_endpoint?: string;
  azure_deployment?: string;
  tavily_api_key?: string;
}

// Long enough to outlast a container wake with room to spare; short enough
// that a request the platform has dropped still becomes a visible failure.
export const START_TIMEOUT_MS = 60_000;

export async function fetchDemos(timeoutMs?: number): Promise<Demo[]> {
  // The timeout is what turns a sleeping server into a retry rather than a
  // request that hangs as long as the browser allows.
  const response = await fetch("/api/demos", {
    signal: timeoutMs === undefined ? null : AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error("could not load the demo list");
  const payload = (await response.json()) as { demos: Demo[] };
  return payload.demos;
}

// Every way this can fail becomes an Error whose message is a sentence a
// visitor can act on: the server's own refusal when it sent one, and plain
// wording for the paths that never reach it or come back as something other
// than JSON — a dropped connection, a timeout, a proxy's error page.
export async function createSession(
  body: CreateSessionBody,
  timeoutMs: number = START_TIMEOUT_MS,
): Promise<string> {
  let response: Response;
  try {
    response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (cause) {
    throw new Error(describeTransportFailure(cause));
  }
  const payload = (await response.json().catch(() => null)) as {
    session_id?: unknown;
    error?: { message?: unknown };
  } | null;
  if (!response.ok) {
    const sent = payload?.error?.message;
    throw new Error(
      typeof sent === "string"
        ? sent
        : `the server answered with status ${response.status} instead of a session; try again in a moment`,
    );
  }
  if (typeof payload?.session_id !== "string") {
    throw new Error("the server answered without a session id; try again in a moment");
  }
  return payload.session_id;
}

export function describeTransportFailure(cause: unknown): string {
  return isTimeout(cause)
    ? "the server did not answer within a minute - it may still be waking; try again"
    : "the request never reached the server - check the connection and try again";
}

function isTimeout(cause: unknown): boolean {
  const seen = new Set<unknown>();
  let current = cause;
  while (typeof current === "object" && current !== null && !seen.has(current)) {
    seen.add(current);
    const name = (current as { name?: unknown }).name;
    if (name === "TimeoutError" || name === "AbortError") return true;
    current = (current as { cause?: unknown }).cause;
  }
  return false;
}

// The socket shares the page's host and follows its scheme: a page served
// over https must open wss, or the browser refuses the connection silently.
export function streamUrl(
  sessionId: string,
  location: { protocol: string; host: string } = window.location,
): string {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/api/sessions/${sessionId}/stream`;
}

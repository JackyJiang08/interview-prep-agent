import type { Demo } from "./types";

export interface CreateSessionBody {
  mode: "demo" | "live";
  demo_id?: string;
  jd_text?: string;
  evidence_text?: string;
  evidence_format?: "yaml" | "markdown";
  round_text?: string;
  gemini_api_key?: string;
}

export async function fetchDemos(): Promise<Demo[]> {
  const response = await fetch("/api/demos");
  if (!response.ok) throw new Error("could not load the demo list");
  const payload = (await response.json()) as { demos: Demo[] };
  return payload.demos;
}

export async function createSession(body: CreateSessionBody): Promise<string> {
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    const message = payload?.error?.message ?? "the session could not be created";
    throw new Error(message);
  }
  return payload.session_id as string;
}

export function streamUrl(sessionId: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/sessions/${sessionId}/stream`;
}

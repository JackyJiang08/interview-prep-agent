// The deployed demo scales to zero, so the first request after idle can
// spend several seconds waiting for the container to wake — and the landing
// page's demo fetch is the request that meets it. This state machine owns
// that experience: the first attempt runs silently, any failure or timeout
// moves to "waking" and schedules a retry, and retries back off up to a
// ceiling until the list loads. Components render the state and run the
// timers; every transition and every delay is decided here.

export const FETCH_TIMEOUT_MS = 4000;
const FIRST_RETRY_MS = 1500;
const RETRY_CEILING_MS = 8000;

export type WakePhase = "first_try" | "waking" | "ready";

export interface WakeState {
  phase: WakePhase;
  attempt: number; // attempts completed so far, every one failed
}

export const initialWakeState: WakeState = { phase: "first_try", attempt: 0 };

export type WakeAction = { kind: "attempt_failed" } | { kind: "loaded" };

export function wakeReducer(state: WakeState, action: WakeAction): WakeState {
  switch (action.kind) {
    case "attempt_failed":
      if (state.phase === "ready") return state;
      return { phase: "waking", attempt: state.attempt + 1 };
    case "loaded":
      return { ...state, phase: "ready" };
  }
}

export function retryDelayMs(attempt: number): number {
  if (attempt <= 0) return 0;
  return Math.min(FIRST_RETRY_MS * 2 ** (attempt - 1), RETRY_CEILING_MS);
}

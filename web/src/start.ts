// What the page shows between a click on a start button and the run
// screen. The rule this encodes: a click never produces nothing. Every
// state reachable after "clicked" carries a line the visitor can read — the
// button's own label at first, the wake explanation once the wait grows
// past what a warm server takes, and the failure's sentence if it fails.

export type StartWhere = "sample" | "own" | "demos";

export type StartState =
  | { phase: "idle" }
  | { phase: "starting"; where: StartWhere; slow: boolean }
  | { phase: "failed"; where: StartWhere; message: string };

export type StartAction =
  | { kind: "clicked"; where: StartWhere }
  | { kind: "still_waiting" }
  | { kind: "failed"; message: string }
  | { kind: "dismissed" };

// A warm server creates a session well under a second; past this, the
// visitor is almost certainly waiting on a container wake and is told so.
export const SLOW_START_MS = 1500;

export const idleStart: StartState = { phase: "idle" };

export const WAKE_LINE =
  "Starting the server — this demo sleeps when idle and takes a few seconds to wake.";

export function startReducer(state: StartState, action: StartAction): StartState {
  switch (action.kind) {
    case "clicked":
      return { phase: "starting", where: action.where, slow: false };
    case "still_waiting":
      return state.phase === "starting" ? { ...state, slow: true } : state;
    case "failed":
      return state.phase === "starting"
        ? { phase: "failed", where: state.where, message: action.message }
        : state;
    case "dismissed":
      return idleStart;
  }
}

// The one line shown for a state, or null only when idle.
export function visibleLine(state: StartState): string | null {
  switch (state.phase) {
    case "idle":
      return null;
    case "starting":
      return state.slow ? WAKE_LINE : "Starting the run";
    case "failed":
      return state.message;
  }
}

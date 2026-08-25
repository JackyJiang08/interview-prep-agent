// The one place protocol knowledge lives. Every socket message passes
// through here as an untyped value and comes out as UI state; components
// never read raw messages. Unknown messages change nothing.

import type { EvidenceItem, PrepPackage } from "./types";

export type Phase =
  | "connecting"
  | "running"
  | "waiting_for_answer"
  | "assessing"
  | "completed"
  | "failed"
  | "disconnected";

export interface StageEntry {
  node: string;
  summary: string;
}

export interface PendingInterrupt {
  requirementId: string;
  question: string;
  answer: string | null;
}

export interface Resolution {
  requirementId: string;
  question: string;
  answer: string;
  accepted: boolean;
  acceptedClaim: string | null;
  mintedId: string | null;
  decisionReason: string;
}

export interface RunState {
  phase: Phase;
  stages: StageEntry[];
  pending: PendingInterrupt | null;
  resolutions: Resolution[];
  prepPackage: PrepPackage | null;
  evidence: EvidenceItem[];
  stopReason: string | null;
  error: { category: string; message: string } | null;
}

export const initialRunState: RunState = {
  phase: "connecting",
  stages: [],
  pending: null,
  resolutions: [],
  prepPackage: null,
  evidence: [],
  stopReason: null,
  error: null,
};

export type RunAction =
  | { kind: "message"; message: unknown }
  | { kind: "answer_submitted"; text: string }
  | { kind: "socket_closed" };

const TERMINAL: Phase[] = ["completed", "failed"];

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.kind) {
    case "answer_submitted":
      if (state.pending === null) return state;
      return {
        ...state,
        phase: "assessing",
        pending: { ...state.pending, answer: action.text },
      };
    case "socket_closed":
      if (TERMINAL.includes(state.phase)) return state;
      return { ...state, phase: "disconnected" };
    case "message":
      return applyMessage(state, action.message);
  }
}

function applyMessage(state: RunState, raw: unknown): RunState {
  if (typeof raw !== "object" || raw === null) return state;
  const message = raw as Record<string, unknown>;

  switch (message.type) {
    case "node_update":
      return applyNodeUpdate(state, message);
    case "interrupt": {
      if (
        typeof message.requirement_id !== "string" ||
        typeof message.question !== "string"
      ) {
        return state;
      }
      return {
        ...state,
        phase: "waiting_for_answer",
        pending: {
          requirementId: message.requirement_id,
          question: message.question,
          answer: null,
        },
      };
    }
    case "package": {
      const evidence = Array.isArray(message.evidence)
        ? (message.evidence as EvidenceItem[])
        : [];
      return {
        ...state,
        prepPackage: (message.package as PrepPackage) ?? null,
        evidence,
      };
    }
    case "done": {
      const stopReason =
        typeof message.stop_reason === "string" ? message.stop_reason : null;
      return {
        ...state,
        phase: state.error === null ? "completed" : "failed",
        stopReason,
        pending: null,
      };
    }
    case "error": {
      return {
        ...state,
        phase: "failed",
        error: {
          category: String(message.category ?? "unknown"),
          message: String(message.message ?? "the run failed"),
        },
      };
    }
    default:
      return state;
  }
}

function applyNodeUpdate(
  state: RunState,
  message: Record<string, unknown>,
): RunState {
  const node = typeof message.node === "string" ? message.node : "unknown";
  const delta = (message.delta ?? {}) as Record<string, unknown>;

  let next = state;
  if (node === "assess_and_admit" && typeof delta.record === "object") {
    next = resolvePending(state, delta.record as Record<string, unknown>);
  }
  const entry: StageEntry = { node, summary: summarize(node, delta) };
  return { ...next, stages: [...next.stages, entry] };
}

function resolvePending(
  state: RunState,
  record: Record<string, unknown>,
): RunState {
  const accepted = record.accepted === true;
  const mintedId = accepted
    ? `CL-${String(
        state.resolutions.filter((item) => item.accepted).length + 1,
      ).padStart(3, "0")}`
    : null;
  const resolution: Resolution = {
    requirementId: String(record.requirement_id ?? ""),
    question: String(record.question ?? state.pending?.question ?? ""),
    answer: String(record.answer ?? state.pending?.answer ?? ""),
    accepted,
    acceptedClaim:
      typeof record.accepted_claim === "string" ? record.accepted_claim : null,
    mintedId,
    decisionReason: String(record.decision_reason ?? ""),
  };
  return {
    ...state,
    phase: "running",
    pending: null,
    resolutions: [...state.resolutions, resolution],
  };
}

function summarize(node: string, delta: Record<string, unknown>): string {
  switch (node) {
    case "parse_round": {
      const round = delta.round as Record<string, unknown> | null | undefined;
      return round && typeof round.round_type === "string"
        ? `round context: ${round.round_type}`
        : "no round context; preparing generally";
    }
    case "generate_initial":
      return delta.package_valid
        ? "initial package generated and valid"
        : "initial package failed validation";
    case "observe": {
      if (typeof delta.stop_reason === "string") return "action budget exhausted";
      if (typeof delta.selected === "string")
        return `next gap selected: ${delta.selected}`;
      return delta.question_budget_left === false
        ? "question ceiling reached; moving to final generation"
        : "gap queue empty; moving to final generation";
    }
    case "ask":
      return "waiting for one factual answer";
    case "assess_and_admit": {
      const record = delta.record as Record<string, unknown> | undefined;
      if (record === undefined) return "answer assessed";
      return record.accepted === true
        ? `admitted for ${String(record.requirement_id)}`
        : `not admitted for ${String(record.requirement_id)}`;
    }
    case "generate_final": {
      const base = delta.package_valid
        ? "final package generated and valid"
        : "final package failed validation";
      return typeof delta.note === "string" ? `${base} (${delta.note})` : base;
    }
    case "invalid":
      return "terminated without a package";
    case "stop":
      return typeof delta.stop_reason === "string"
        ? `stopped: ${delta.stop_reason.split("_").join(" ")}`
        : "stopped";
    default:
      return "";
  }
}

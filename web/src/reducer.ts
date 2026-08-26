// The one place protocol knowledge lives. Every socket message passes
// through here as an untyped value and comes out as UI state; components
// never read raw messages. Unknown messages change nothing.

import type { EvidenceItem, PrepPackage, ResearchFinding } from "./types";

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
  startedAt: number | null; // wall-clock arrival, for the elapsed display
}

// Where the run is inside a generation, derived from the server's progress
// events and the known graph shape: never a percentage, always a stage.
export interface Progress {
  stage: string;
  index: number;
  total: number;
  label: string;
  note: string | null; // one quiet line for the long model stages
  startedAt: number | null;
}

const STAGE_LABELS: Record<string, string> = {
  extract_evidence: "reading your evidence",
  extract_requirements: "reading the posting for requirements",
  match: "matching evidence to requirements",
  assess_gaps: "assessing the gaps",
  research: "gathering role research",
  build_strategy: "building the strategy",
  generate_questions: "writing practice questions",
  validate_package: "checking the package",
};

const STAGE_NOTES: Record<string, string> = {
  build_strategy:
    "The model is writing your positioning, the stories to prepare, and the risks to address.",
  generate_questions:
    "The model is writing practice questions with follow-ups and answer outlines.",
};

export function describeProgress(stage: string): { label: string; note: string | null } {
  return {
    label: STAGE_LABELS[stage] ?? stage.split("_").join(" "),
    note: STAGE_NOTES[stage] ?? null,
  };
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
  progress: Progress | null;
  prepPackage: PrepPackage | null;
  evidence: EvidenceItem[];
  research: ResearchFinding[];
  stopReason: string | null;
  error: { category: string; message: string } | null;
}

export const initialRunState: RunState = {
  phase: "connecting",
  stages: [],
  pending: null,
  resolutions: [],
  progress: null,
  prepPackage: null,
  evidence: [],
  research: [],
  stopReason: null,
  error: null,
};

// A message may carry the wall-clock time it arrived; the reducer stores it
// and never reads a clock itself, so every transition stays testable.
export type RunAction =
  | { kind: "message"; message: unknown; at?: number }
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
      return applyMessage(state, action.message, action.at ?? null);
  }
}

function applyMessage(state: RunState, raw: unknown, at: number | null): RunState {
  if (typeof raw !== "object" || raw === null) return state;
  const message = raw as Record<string, unknown>;

  switch (message.type) {
    case "node_update":
      return applyNodeUpdate(state, message, at);
    case "progress": {
      if (
        typeof message.stage !== "string" ||
        typeof message.index !== "number" ||
        typeof message.total !== "number"
      ) {
        return state;
      }
      const { label, note } = describeProgress(message.stage);
      return {
        ...state,
        phase: state.phase === "connecting" ? "running" : state.phase,
        progress: {
          stage: message.stage,
          index: message.index,
          total: message.total,
          label,
          note,
          startedAt: at,
        },
      };
    }
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
        progress: null,
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
      const research = Array.isArray(message.research)
        ? (message.research as ResearchFinding[])
        : [];
      return {
        ...state,
        prepPackage: (message.package as PrepPackage) ?? null,
        evidence,
        research,
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
        progress: null,
      };
    }
    case "error": {
      return {
        ...state,
        phase: "failed",
        progress: null,
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
  at: number | null,
): RunState {
  const node = typeof message.node === "string" ? message.node : "unknown";
  const delta = (message.delta ?? {}) as Record<string, unknown>;

  let next = state;
  if (node === "assess_and_admit" && typeof delta.record === "object") {
    next = resolvePending(state, delta.record as Record<string, unknown>);
  }
  const entry: StageEntry = { node, summary: summarize(node, delta), startedAt: at };
  // A generation has finished once its node update arrives.
  const progress =
    node === "generate_initial" || node === "generate_final" ? null : next.progress;
  return { ...next, stages: [...next.stages, entry], progress };
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

// Lines the guard refused as not being requirements, never hidden.
function droppedNote(delta: Record<string, unknown>): string {
  const dropped = delta.dropped;
  if (!Array.isArray(dropped) || dropped.length === 0) return "";
  return `; ${dropped.length} line${dropped.length === 1 ? "" : "s"} set aside as not requirements`;
}

function summarize(node: string, delta: Record<string, unknown>): string {
  switch (node) {
    case "parse_round": {
      const round = delta.round as Record<string, unknown> | null | undefined;
      return round && typeof round.round_type === "string"
        ? `round context: ${round.round_type}`
        : "no round context; preparing generally";
    }
    case "generate_initial": {
      const base = delta.package_valid
        ? "initial package generated and valid"
        : "initial package failed validation";
      return `${base}${droppedNote(delta)}`;
    }
    case "observe": {
      if (typeof delta.stop_reason === "string") return "action budget exhausted";
      if (typeof delta.selected === "string")
        return `next gap selected: ${delta.selected}`;
      return delta.question_budget_left === false
        ? "question ceiling reached; moving to final generation"
        : "gap queue empty; moving to final generation";
    }
    case "research": {
      const findings = delta.research_findings;
      const count = Array.isArray(findings) ? findings.length : 0;
      return count === 0
        ? "no role research supplied; preparing from the posting alone"
        : `${count} research finding${count === 1 ? "" : "s"} gathered`;
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
      const noted = typeof delta.note === "string" ? `${base} (${delta.note})` : base;
      return `${noted}${droppedNote(delta)}`;
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

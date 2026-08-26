import { describe, expect, it } from "vitest";

import {
  initialRunState,
  runReducer,
  type RunAction,
  type RunState,
} from "./reducer";

function play(actions: RunAction[], from: RunState = initialRunState): RunState {
  return actions.reduce(runReducer, from);
}

const msg = (message: unknown): RunAction => ({ kind: "message", message });

const INTERRUPT = msg({
  type: "interrupt",
  requirement_id: "REQ-002",
  question: "Share one specific example that demonstrates this requirement: X.",
  context: {},
});

const ADMITTED_RECORD = msg({
  type: "node_update",
  node: "assess_and_admit",
  delta: {
    record: {
      requirement_id: "REQ-002",
      question: "Q",
      answer: "A concrete answer with enough substance.",
      accepted: true,
      decision_reason: "every code-owned admission gate passed",
      accepted_claim: "A concrete admitted claim.",
    },
  },
});

const REJECTED_RECORD = msg({
  type: "node_update",
  node: "assess_and_admit",
  delta: {
    record: {
      requirement_id: "REQ-005",
      question: "Q2",
      answer: "An aspiration, not experience.",
      accepted: false,
      decision_reason: "admission: the assessment rejected the answer",
      accepted_claim: null,
    },
  },
});

describe("event ordering", () => {
  it("collects stage entries in arrival order", () => {
    const state = play([
      msg({ type: "node_update", node: "parse_round", delta: { round: null } }),
      msg({
        type: "node_update",
        node: "generate_initial",
        delta: { package_valid: true },
      }),
      msg({
        type: "node_update",
        node: "observe",
        delta: { selected: "REQ-002", question_budget_left: true },
      }),
    ]);
    expect(state.stages.map((entry) => entry.node)).toEqual([
      "parse_round",
      "generate_initial",
      "observe",
    ]);
    expect(state.stages[2].summary).toContain("REQ-002");
    expect(state.phase).toBe("connecting");
  });
});

describe("interrupt, answer, verdict", () => {
  it("walks waiting -> assessing -> resolved admitted with a minted id", () => {
    let state = play([INTERRUPT]);
    expect(state.phase).toBe("waiting_for_answer");
    expect(state.pending?.requirementId).toBe("REQ-002");

    state = runReducer(state, {
      kind: "answer_submitted",
      text: "A concrete answer with enough substance.",
    });
    expect(state.phase).toBe("assessing");

    state = runReducer(state, ADMITTED_RECORD);
    expect(state.phase).toBe("running");
    expect(state.pending).toBeNull();
    expect(state.resolutions).toHaveLength(1);
    expect(state.resolutions[0].accepted).toBe(true);
    expect(state.resolutions[0].mintedId).toBe("CL-001");
    expect(state.resolutions[0].acceptedClaim).toBe("A concrete admitted claim.");
  });

  it("resolves a rejection with its reason and no minted id", () => {
    let state = play([INTERRUPT]);
    state = runReducer(state, { kind: "answer_submitted", text: "..." });
    state = runReducer(state, REJECTED_RECORD);
    expect(state.resolutions[0].accepted).toBe(false);
    expect(state.resolutions[0].mintedId).toBeNull();
    expect(state.resolutions[0].decisionReason).toContain("rejected");
  });

  it("numbers minted ids by admitted count, skipping rejections", () => {
    let state = play([INTERRUPT]);
    state = runReducer(state, { kind: "answer_submitted", text: "a" });
    state = runReducer(state, ADMITTED_RECORD);
    state = runReducer(state, INTERRUPT);
    state = runReducer(state, { kind: "answer_submitted", text: "b" });
    state = runReducer(state, REJECTED_RECORD);
    state = runReducer(state, INTERRUPT);
    state = runReducer(state, { kind: "answer_submitted", text: "c" });
    state = runReducer(state, ADMITTED_RECORD);
    expect(state.resolutions.map((item) => item.mintedId)).toEqual([
      "CL-001",
      null,
      "CL-002",
    ]);
  });
});

describe("terminal states", () => {
  it("completes with a stop reason and keeps the package", () => {
    const state = play([
      msg({
        type: "package",
        package: { requirements: [], matches: [], focus_areas: [], strategy: null, mock_questions: [] },
        evidence: [{ id: "EV-001", summary: "an item" }],
      }),
      msg({ type: "done", stop_reason: "valid_package_complete" }),
    ]);
    expect(state.phase).toBe("completed");
    expect(state.stopReason).toBe("valid_package_complete");
    expect(state.evidence).toHaveLength(1);
    expect(state.prepPackage).not.toBeNull();
  });

  it("an error then done stays failed", () => {
    const state = play([
      msg({ type: "error", category: "gate", message: "a guarantee failed" }),
      msg({ type: "done", stop_reason: null }),
    ]);
    expect(state.phase).toBe("failed");
    expect(state.error?.category).toBe("gate");
  });

  it("a dropped socket mid-run reads as disconnected, not after the end", () => {
    const midRun = play([INTERRUPT]);
    expect(runReducer(midRun, { kind: "socket_closed" }).phase).toBe(
      "disconnected",
    );
    const done = play([msg({ type: "done", stop_reason: "valid_package_complete" })]);
    expect(runReducer(done, { kind: "socket_closed" }).phase).toBe("completed");
  });
});

describe("unknown input", () => {
  it("unknown message types change nothing and never throw", () => {
    const before = play([INTERRUPT]);
    for (const weird of [
      { type: "telemetry", noise: true },
      { no_type: 1 },
      null,
      undefined,
      42,
      "text",
      [],
    ]) {
      expect(runReducer(before, msg(weird))).toEqual(before);
    }
  });

  it("an answer without a pending interrupt is a no-op", () => {
    expect(
      runReducer(initialRunState, { kind: "answer_submitted", text: "x" }),
    ).toEqual(initialRunState);
  });
});

describe("guarded extraction", () => {
  it("names the lines the guard set aside, never hiding them", () => {
    const state = play([
      msg({
        type: "node_update",
        node: "generate_initial",
        delta: {
          package_valid: true,
          dropped: [
            { id: "REQ-001", text: "Job description", reason: "reads as a section heading" },
            { id: "REQ-009", text: "Salary range $90,000", reason: "reads as a salary statement" },
          ],
        },
      }),
    ]);
    expect(state.stages[0].summary).toBe(
      "initial package generated and valid; 2 lines set aside as not requirements",
    );
  });
});

describe("research findings", () => {
  it("carries findings off the package event", () => {
    const state = play([
      msg({
        type: "package",
        package: { requirements: [], matches: [], focus_areas: [], strategy: null, mock_questions: [] },
        evidence: [],
        research: [
          {
            finding_id: "SRC-001",
            source_kind: "search",
            title: "Reported themes",
            summary: "A summary.",
            url: "https://example.org/a",
            retrieved_for: "a query",
          },
        ],
      }),
      msg({ type: "done", stop_reason: "valid_package_complete" }),
    ]);
    expect(state.research).toHaveLength(1);
    expect(state.research[0].finding_id).toBe("SRC-001");
    expect(state.research[0].url).toBe("https://example.org/a");
  });

  it("defaults to no findings when the package carries none", () => {
    const state = play([
      msg({
        type: "package",
        package: { requirements: [], matches: [], focus_areas: [], strategy: null, mock_questions: [] },
        evidence: [],
      }),
    ]);
    expect(state.research).toEqual([]);
  });

  it("summarizes the research stage by finding count", () => {
    const none = play([
      msg({ type: "node_update", node: "research", delta: { research_findings: [] } }),
    ]);
    expect(none.stages[0].summary).toContain("no role research");
    const some = play([
      msg({
        type: "node_update",
        node: "research",
        delta: { research_findings: [{ finding_id: "SRC-001" }, { finding_id: "SRC-002" }] },
      }),
    ]);
    expect(some.stages[0].summary).toBe("2 research findings gathered");
  });
});

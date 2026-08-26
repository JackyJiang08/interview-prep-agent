import { describe, expect, it } from "vitest";

import { flowReducer, initialFlow, type FlowAction, type FlowState } from "./flow";
import { initialForm } from "./form";
import { initialRunState, runReducer } from "./reducer";

function play(actions: FlowAction[], from: FlowState = initialFlow): FlowState {
  return actions.reduce(flowReducer, from);
}

const FILLED: FlowAction[] = [
  { kind: "form", action: { kind: "set", patch: { jdText: "Requirements\n- SQL" } } },
  {
    kind: "form",
    action: {
      kind: "set",
      patch: { resume: { filename: "resume.pdf", text: "## Skills\n- SQL, Python" } },
    },
  },
  { kind: "form", action: { kind: "set", patch: { apiKey: "key-1234", provider: "anthropic" } } },
  { kind: "form", action: { kind: "set", patch: { roundText: "Technical screen" } } },
  { kind: "form", action: { kind: "toggle", section: "advanced" } },
  { kind: "form", action: { kind: "toggle", section: "preview" } },
];

describe("the form survives the run", () => {
  it("fill, start, fail, back: every field is as it was", () => {
    const filled = play(FILLED);
    expect(filled.screen).toBe("landing");
    expect(filled.form.jdText).toBe("Requirements\n- SQL");
    expect(filled.form.open).toEqual({ advanced: true, demos: false, preview: true });

    const running = flowReducer(filled, { kind: "started", sessionId: "s-1" });
    expect(running.screen).toBe("run");
    expect(running.sessionId).toBe("s-1");

    // The run fails on its own screen; that state lives beside the flow,
    // never inside the form.
    const failedRun = runReducer(initialRunState, {
      kind: "message",
      message: { type: "error", category: "gate", message: "a guarantee failed" },
    });
    expect(failedRun.phase).toBe("failed");

    const back = flowReducer(running, { kind: "back" });
    expect(back.screen).toBe("landing");
    expect(back.sessionId).toBeNull();
    expect(back.form).toEqual(filled.form);
    expect(back.form.resume.filename).toBe("resume.pdf");
    expect(back.form.apiKey).toBe("key-1234");
    expect(back.form.provider).toBe("anthropic");
  });

  it("a failed start on the landing changes nothing in the form either", () => {
    // Nothing in the flow moves when session creation fails; the page's
    // start state carries the failure, and the form stays exactly filled.
    const filled = play(FILLED);
    expect(play([], filled)).toEqual(filled);
  });

  it("starts empty and edits only what a patch names", () => {
    expect(initialFlow.form).toEqual(initialForm);
    const one = play([{ kind: "form", action: { kind: "set", patch: { jdText: "x" } } }]);
    expect(one.form).toEqual({ ...initialForm, jdText: "x" });
  });
});

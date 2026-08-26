import { describe, expect, it } from "vitest";

import {
  idleStart,
  startReducer,
  visibleLine,
  WAKE_LINE,
  type StartAction,
  type StartState,
} from "./start";

const clicked: StartAction = { kind: "clicked", where: "sample" };

describe("a click never produces nothing", () => {
  it("every state reachable after a click carries a visible line", () => {
    // Walk every sequence of follow-up actions up to three deep from a click
    // and check the invariant on each state along the way.
    const followUps: StartAction[] = [
      { kind: "still_waiting" },
      { kind: "failed", message: "the server answered with status 504" },
      clicked,
    ];
    const reached: StartState[] = [];
    const walk = (state: StartState, depth: number) => {
      reached.push(state);
      if (depth === 0) return;
      for (const action of followUps) walk(startReducer(state, action), depth - 1);
    };
    walk(startReducer(idleStart, clicked), 3);
    expect(reached.length).toBeGreaterThan(10);
    for (const state of reached) {
      expect(state.phase).not.toBe("idle");
      expect(visibleLine(state)).toBeTruthy();
    }
  });

  it("names the wake once the wait grows past a warm server's answer", () => {
    const starting = startReducer(idleStart, clicked);
    expect(visibleLine(starting)).toBe("Starting the run");
    const slow = startReducer(starting, { kind: "still_waiting" });
    expect(visibleLine(slow)).toBe(WAKE_LINE);
  });

  it("keeps the failure next to the action that produced it", () => {
    const failed = startReducer(startReducer(idleStart, { kind: "clicked", where: "own" }), {
      kind: "failed",
      message: "the request never reached the server",
    });
    expect(failed).toEqual({
      phase: "failed",
      where: "own",
      message: "the request never reached the server",
    });
    expect(visibleLine(failed)).toContain("never reached");
  });

  it("only a dismissal returns to idle; stray timers and failures change nothing there", () => {
    expect(startReducer(idleStart, { kind: "still_waiting" })).toBe(idleStart);
    expect(startReducer(idleStart, { kind: "failed", message: "x" })).toBe(idleStart);
    const failed = startReducer(startReducer(idleStart, clicked), { kind: "failed", message: "x" });
    expect(startReducer(failed, { kind: "dismissed" })).toEqual(idleStart);
  });
});

import { describe, expect, it } from "vitest";

import {
  initialWakeState,
  retryDelayMs,
  wakeReducer,
  type WakeState,
} from "./wake";

describe("the wake state machine", () => {
  it("starts silent: the first attempt carries no explanation", () => {
    expect(initialWakeState.phase).toBe("first_try");
    expect(initialWakeState.attempt).toBe(0);
  });

  it("moves to waking on the first failure and counts the attempt", () => {
    const state = wakeReducer(initialWakeState, { kind: "attempt_failed" });
    expect(state.phase).toBe("waking");
    expect(state.attempt).toBe(1);
  });

  it("stays waking across repeated failures, counting each one", () => {
    let state: WakeState = initialWakeState;
    for (let i = 1; i <= 4; i++) {
      state = wakeReducer(state, { kind: "attempt_failed" });
      expect(state.phase).toBe("waking");
      expect(state.attempt).toBe(i);
    }
  });

  it("resolves to ready from either phase once the list loads", () => {
    expect(wakeReducer(initialWakeState, { kind: "loaded" }).phase).toBe("ready");
    const waking = wakeReducer(initialWakeState, { kind: "attempt_failed" });
    expect(wakeReducer(waking, { kind: "loaded" }).phase).toBe("ready");
  });

  it("ignores a stale failure after the list has loaded", () => {
    const ready = wakeReducer(initialWakeState, { kind: "loaded" });
    expect(wakeReducer(ready, { kind: "attempt_failed" })).toEqual(ready);
  });

  it("retries immediately once, then backs off to a ceiling", () => {
    expect(retryDelayMs(0)).toBe(0);
    const delays = [1, 2, 3, 4, 5, 9].map(retryDelayMs);
    for (let i = 1; i < delays.length; i++) {
      expect(delays[i]).toBeGreaterThanOrEqual(delays[i - 1]);
    }
    expect(delays[0]).toBeGreaterThan(0);
    expect(Math.max(...delays)).toBe(retryDelayMs(9));
    expect(retryDelayMs(9)).toBe(retryDelayMs(100)); // capped, never unbounded
  });
});

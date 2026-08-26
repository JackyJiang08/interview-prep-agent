import { describe, expect, it } from "vitest";

import { disclosureReducer, initialDisclosure } from "./disclosure";

describe("the collapsed sections", () => {
  it("both start closed, so the first visitor meets the primary flow", () => {
    expect(initialDisclosure).toEqual({ advanced: false, demos: false });
  });

  it("toggling opens and closes one section without touching the other", () => {
    let state = disclosureReducer(initialDisclosure, { kind: "toggle", section: "advanced" });
    expect(state).toEqual({ advanced: true, demos: false });
    state = disclosureReducer(state, { kind: "toggle", section: "demos" });
    expect(state).toEqual({ advanced: true, demos: true });
    state = disclosureReducer(state, { kind: "toggle", section: "advanced" });
    expect(state).toEqual({ advanced: false, demos: true });
  });

  it("opening is idempotent: an open section stays open and the state is unchanged", () => {
    const opened = disclosureReducer(initialDisclosure, { kind: "open", section: "demos" });
    expect(opened.demos).toBe(true);
    expect(disclosureReducer(opened, { kind: "open", section: "demos" })).toBe(opened);
  });
});

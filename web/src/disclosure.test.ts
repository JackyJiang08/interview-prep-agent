import { describe, expect, it } from "vitest";

import { disclosureReducer, initialDisclosure } from "./disclosure";

describe("the collapsed sections", () => {
  it("all start closed, so the first visitor meets the form", () => {
    expect(initialDisclosure).toEqual({ advanced: false, demos: false, preview: false });
  });

  it("toggling opens and closes one section without touching the other", () => {
    let state = disclosureReducer(initialDisclosure, { kind: "toggle", section: "advanced" });
    expect(state).toEqual({ advanced: true, demos: false, preview: false });
    state = disclosureReducer(state, { kind: "toggle", section: "demos" });
    expect(state).toEqual({ advanced: true, demos: true, preview: false });
    state = disclosureReducer(state, { kind: "toggle", section: "advanced" });
    expect(state).toEqual({ advanced: false, demos: true, preview: false });
    state = disclosureReducer(state, { kind: "toggle", section: "preview" });
    expect(state.preview).toBe(true);
  });

  it("opening is idempotent: an open section stays open and the state is unchanged", () => {
    const opened = disclosureReducer(initialDisclosure, { kind: "open", section: "demos" });
    expect(opened.demos).toBe(true);
    expect(disclosureReducer(opened, { kind: "open", section: "demos" })).toBe(opened);
  });
});

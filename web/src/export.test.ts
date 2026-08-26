import { describe, expect, it } from "vitest";

import { coverageCounts, packageMarkdown, questionsMarkdown } from "./export";
import type { PrepPackage } from "./types";

const PACKAGE: PrepPackage = {
  requirements: [
    { id: "REQ-001", text: "Strong SQL | Python" },
    { id: "REQ-002", text: "Designing experiments" },
  ],
  matches: [
    {
      requirement_id: "REQ-001",
      status: "PROOF",
      coverage: "FULL",
      matches: [{ evidence_id: "EV-001", score: 0.8 }],
      method: "lexical-idf-v1",
    },
    { requirement_id: "REQ-002", status: "GAP", coverage: "GAP", matches: [], method: "lexical-idf-v1" },
  ],
  focus_areas: [],
  strategy: {
    top_priorities: [
      {
        requirement_id: "REQ-001",
        evidence_ids: ["EV-001"],
        preparation_theme: "Lead with analysis",
        rationale: "Strongest support.",
      },
    ],
    positioning_statement: "An analyst with attested depth.",
    stories_to_prepare: [],
    risks_to_address: [
      { requirement_id: "REQ-002", risk: "May be probed.", mitigation: "Answer honestly." },
    ],
  },
  mock_questions: [
    {
      question: "Tell me about a query you tuned.",
      requirement_id: "REQ-001",
      capability_tested: "sql",
      evidence_ids: ["EV-001"],
      follow_up_probe: "What changed?",
      answer_outline: ["Context.", "Outcome."],
    },
  ],
};

describe("markdown export", () => {
  it("assembles the package from session data with every citation kept", () => {
    const text = packageMarkdown({
      prepPackage: PACKAGE,
      evidence: [{ id: "EV-001", summary: "Owned SQL analysis", source: "Work" }],
      research: [
        {
          finding_id: "SRC-001",
          source_kind: "search",
          title: "Reported themes",
          summary: "Experiments come up.",
          url: "https://example.org/a",
          retrieved_for: "q",
        },
      ],
      resolutions: [
        {
          requirementId: "REQ-002",
          question: "Q",
          answer: "",
          accepted: false,
          acceptedClaim: null,
          mintedId: null,
          decisionReason: "skipped by the candidate; no answer was given",
        },
      ],
    });
    expect(text.startsWith("# Interview preparation package\n")).toBe(true);
    expect(text).toContain("2 requirements: 1 covered, 0 partly covered, 1 open gaps.");
    expect(text).toContain("| REQ-001 Strong SQL \\| Python | FULL | EV-001 |");
    expect(text).toContain("| REQ-002 Designing experiments | GAP | none |");
    expect(text).toContain("**Lead with analysis** (REQ-001; EV-001)");
    expect(text).toContain("- REQ-002: May be probed. Mitigation: Answer honestly.");
    expect(text).toContain("## Practice questions");
    expect(text).toContain("- **EV-001**: Owned SQL analysis (Work)");
    expect(text).toContain("- **SRC-001**: Reported themes. Experiments come up. https://example.org/a");
    expect(text).toContain("- REQ-002: recorded, not admitted. skipped by the candidate");
    expect(text.endsWith("\n")).toBe(true);
  });

  it("writes the practice questions as a numbered list with probes and outlines", () => {
    const text = questionsMarkdown(PACKAGE);
    expect(text).toContain("# Practice questions");
    expect(text).toContain("1. **Tell me about a query you tuned.**");
    expect(text).toContain("   - Probes REQ-001; cites EV-001");
    expect(text).toContain("   - Follow-up: What changed?");
    expect(text).toContain("   - Outcome.");
  });

  it("counts coverage, treating a missing level as a gap", () => {
    expect(coverageCounts(PACKAGE)).toEqual({ FULL: 1, PARTIAL: 0, GAP: 1 });
    const missing = { ...PACKAGE, matches: [{ ...PACKAGE.matches[1], coverage: null }] };
    expect(coverageCounts(missing).GAP).toBe(1);
  });
});

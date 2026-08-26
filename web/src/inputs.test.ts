import { describe, expect, it } from "vitest";

import {
  acceptedFile,
  describeExtensions,
  detectEvidenceFormat,
  EVIDENCE_EXTENSIONS,
  INPUT_CEILINGS,
  overCeiling,
  POSTING_EXTENSIONS,
  readTextFile,
} from "./inputs";

const CORPUS = `# Evidence for the quickstart.
- id: EV-001
  summary: >-
    Owned funnel analysis for a subscription product.
  skills:
    - sql
  impact: Cut a reporting cycle from two days to an hour.

- id: EV-002
  summary: Built scheduled pipelines with freshness checks.
`;

const RESUME = `# Jordan Example

## Experience

**Data Analyst, Example Co.** 2022 - present
- Owned funnel analysis for a subscription product, writing SQL against a warehouse
- Built scheduled pipelines with freshness checks

## Skills
- SQL, Python, pandas
`;

describe("evidence format detection", () => {
  it("reads a corpus of id and summary entries as yaml", () => {
    expect(detectEvidenceFormat(CORPUS)).toBe("yaml");
  });

  it("reads a corpus wrapped in an evidence key as yaml", () => {
    expect(detectEvidenceFormat(`evidence:\n  - id: EV-001\n    summary: One thing.\n`)).toBe(
      "yaml",
    );
  });

  it("reads a json corpus as yaml, which it is", () => {
    expect(detectEvidenceFormat(`[{"id": "EV-001", "summary": "One thing."}]`)).toBe("yaml");
  });

  it("reads a markdown resume as markdown", () => {
    expect(detectEvidenceFormat(RESUME)).toBe("markdown");
  });

  it("reads the ambiguous case - bullets that look like keys but carry no corpus - as markdown", () => {
    // A resume written as "- Skill: detail" bullets opens like a yaml sequence
    // of mappings, but nothing in it is an evidence entry.
    const bullets = `- Languages: Python, SQL\n- Tools: dbt, Airflow\n- Summary of role: analytics lead\n`;
    expect(detectEvidenceFormat(bullets)).toBe("markdown");
    // Prose mentioning the words is not a corpus either.
    expect(detectEvidenceFormat("id: summary: these are just words in a line")).toBe("markdown");
  });

  it("reads empty or comment-only text as markdown", () => {
    expect(detectEvidenceFormat("")).toBe("markdown");
    expect(detectEvidenceFormat("# nothing here\n\n")).toBe("markdown");
  });
});

describe("input ceilings", () => {
  it("passes text at the ceiling and refuses one character over, in the server's words", () => {
    expect(overCeiling("jd_text", INPUT_CEILINGS.jd_text)).toBeNull();
    expect(overCeiling("jd_text", INPUT_CEILINGS.jd_text + 1)).toBe(
      "the job posting exceeds the 20,000-character ceiling",
    );
    expect(overCeiling("evidence_text", INPUT_CEILINGS.evidence_text + 1)).toContain("50,000");
  });
});

describe("file reading", () => {
  it("accepts by extension, case-insensitively, and names the accepted kinds", () => {
    expect(acceptedFile("posting.TXT", POSTING_EXTENSIONS)).toBe(true);
    expect(acceptedFile("resume.md", EVIDENCE_EXTENSIONS)).toBe(true);
    expect(acceptedFile("corpus.yml", EVIDENCE_EXTENSIONS)).toBe(true);
    expect(acceptedFile("resume.pdf", EVIDENCE_EXTENSIONS)).toBe(false);
    expect(describeExtensions(POSTING_EXTENSIONS)).toBe(".txt or .md");
    expect(describeExtensions(EVIDENCE_EXTENSIONS)).toBe(".md, .yaml or .yml");
  });

  it("returns the text of an accepted file", async () => {
    const file = new File(["Requirements\n- SQL"], "posting.txt", { type: "text/plain" });
    expect(await readTextFile(file, POSTING_EXTENSIONS, "jd_text")).toEqual({
      text: "Requirements\n- SQL",
    });
  });

  it("refuses the wrong kind without reading it", async () => {
    const file = new File(["%PDF"], "resume.pdf");
    const result = await readTextFile(file, EVIDENCE_EXTENSIONS, "evidence_text");
    expect(result).toEqual({ refusal: "that file is not .md, .yaml or .yml; nothing was read" });
  });

  it("refuses an oversized file with the server's ceiling wording", async () => {
    const file = new File(["x".repeat(INPUT_CEILINGS.round_text + 1)], "round.txt");
    const result = await readTextFile(file, POSTING_EXTENSIONS, "round_text");
    expect(result).toEqual({
      refusal: "the round description exceeds the 2,000-character ceiling; nothing was read",
    });
  });
});

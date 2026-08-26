// Markdown documents assembled from what the session already holds, in the
// browser, so a visitor can keep the package and the questions. Nothing is
// generated server-side; every citation stays the identifier the package used.

import type { Resolution } from "./reducer";
import type { EvidenceItem, PrepPackage, ResearchFinding } from "./types";

export interface ExportInputs {
  prepPackage: PrepPackage;
  evidence: EvidenceItem[];
  research: ResearchFinding[];
  resolutions: Resolution[];
  title?: string;
}

export function packageMarkdown(inputs: ExportInputs): string {
  const { prepPackage, evidence, research, resolutions } = inputs;
  const requirements = new Map(prepPackage.requirements.map((item) => [item.id, item.text]));
  const lines: string[] = [];
  lines.push(`# ${inputs.title ?? "Interview preparation package"}`, "");

  const counts = coverageCounts(prepPackage);
  lines.push(
    `${prepPackage.requirements.length} requirements: ${counts.FULL} covered, ` +
      `${counts.PARTIAL} partly covered, ${counts.GAP} open gaps.`,
    "",
  );

  lines.push("## Coverage", "", "| Requirement | Coverage | Evidence |", "|---|---|---|");
  for (const match of prepPackage.matches) {
    const cited = match.matches.map((item) => item.evidence_id).join(", ") || "none";
    lines.push(
      `| ${match.requirement_id} ${escapeCell(requirements.get(match.requirement_id) ?? "")} | ${match.coverage ?? "GAP"} | ${cited} |`,
    );
  }
  lines.push("");

  lines.push("## Strategy", "", prepPackage.strategy.positioning_statement, "");
  for (const item of prepPackage.strategy.top_priorities) {
    lines.push(
      `- **${item.preparation_theme}** (${item.requirement_id}; ${citeList(item.evidence_ids)}): ${item.rationale}`,
    );
  }
  if (prepPackage.strategy.stories_to_prepare.length > 0) {
    lines.push("", "### Stories to prepare", "");
    for (const story of prepPackage.strategy.stories_to_prepare) {
      lines.push(`- ${story.requirement_id} (${citeList(story.evidence_ids)}): ${story.story_to_prepare}`);
    }
  }
  if (prepPackage.strategy.risks_to_address.length > 0) {
    lines.push("", "### Risks, kept visible", "");
    for (const risk of prepPackage.strategy.risks_to_address) {
      lines.push(`- ${risk.requirement_id}: ${risk.risk} Mitigation: ${risk.mitigation}`);
    }
  }
  lines.push("", questionsMarkdown(prepPackage, false));

  lines.push("## Evidence cited", "");
  for (const item of evidence) {
    lines.push(`- **${item.id}**: ${item.summary}${item.source ? ` (${item.source})` : ""}`);
  }
  if (research.length > 0) {
    lines.push("", "## Role research", "");
    for (const finding of research) {
      lines.push(`- **${finding.finding_id}**: ${finding.title}. ${finding.summary}${finding.url ? ` ${finding.url}` : ""}`);
    }
  }
  if (resolutions.length > 0) {
    lines.push("", "## Questions asked during the run", "");
    for (const resolution of resolutions) {
      const verdict = resolution.accepted
        ? `admitted as ${resolution.mintedId ?? "evidence"}`
        : "recorded, not admitted";
      lines.push(`- ${resolution.requirementId}: ${verdict}. ${resolution.decisionReason}`);
    }
  }
  return lines.join("\n").trimEnd() + "\n";
}

export function questionsMarkdown(prepPackage: PrepPackage, standalone = true): string {
  const lines: string[] = [];
  lines.push(standalone ? "# Practice questions" : "## Practice questions", "");
  prepPackage.mock_questions.forEach((question, index) => {
    lines.push(`${index + 1}. **${question.question}**`);
    lines.push(`   - Probes ${question.requirement_id}${question.evidence_ids.length > 0 ? `; cites ${question.evidence_ids.join(", ")}` : ""}`);
    lines.push(`   - Follow-up: ${question.follow_up_probe}`);
    for (const point of question.answer_outline) lines.push(`   - ${point}`);
    lines.push("");
  });
  return lines.join("\n");
}

export function coverageCounts(prepPackage: PrepPackage): Record<"FULL" | "PARTIAL" | "GAP", number> {
  const counts = { FULL: 0, PARTIAL: 0, GAP: 0 };
  for (const match of prepPackage.matches) counts[match.coverage ?? "GAP"] += 1;
  return counts;
}

function citeList(ids: string[]): string {
  return ids.length > 0 ? ids.join(", ") : "no evidence";
}

function escapeCell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();
}

// A file the browser saves, from text already in memory.
export function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

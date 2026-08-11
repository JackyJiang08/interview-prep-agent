"""Stage 2b - convert coverage verdicts into importance-weighted focus areas.

Deliberately deterministic. The matcher (either path) has already made the one
judgment that needed making; turning verdicts into a preparation ordering is
arithmetic, and arithmetic in code can be tested, reproduced, and argued with
line by line.

Priority is requirement importance multiplied by a coverage weight — a gap on
a critical requirement outranks everything, a fully covered nice-to-have ranks
last. When a requirement carries no importance (the lexical extractor cannot
supply one), the neutral weight 1 is used, so ordering degrades to coverage
alone rather than to a pretended judgment.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models import CoverageLevel, FocusArea, Requirement, RequirementMatch, Status

# A gap costs more preparation than partial cover, which costs more than a
# strength that only needs a story.
COVERAGE_WEIGHT = {
    CoverageLevel.FULL: 1,
    CoverageLevel.PARTIAL: 2,
    CoverageLevel.GAP: 3,
}

PREPARATION_ACTION = {
    CoverageLevel.FULL: "Prepare a concise story that proves this strength.",
    CoverageLevel.PARTIAL: "Strengthen the story and address the unsupported dimension.",
    CoverageLevel.GAP: "Prepare an honest gap response and a concrete learning plan.",
}

# Importance used when the requirement does not carry one.
NEUTRAL_IMPORTANCE = 1


def effective_coverage(verdict: RequirementMatch) -> CoverageLevel:
    """Return the verdict's coverage, deriving it from status when unset.

    Verdicts built before coverage existed carry only the binary status; the
    degenerate mapping is gap to gap and proof to full, which is exactly what
    the lexical matcher would have said.
    """
    if verdict.coverage is not None:
        return verdict.coverage
    return CoverageLevel.GAP if verdict.status is Status.GAP else CoverageLevel.FULL


def build_focus_areas(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
) -> list[FocusArea]:
    """Rank every requirement by where preparation time is best spent.

    Args:
        requirements: The extracted requirements, in source order.
        verdicts: One verdict per requirement, already gate-checked.

    Returns:
        One focus area per requirement, sorted by descending priority; ties
        keep the requirements' source order, so equal priorities read in the
        order the posting stated them.
    """
    by_id = {verdict.requirement_id: verdict for verdict in verdicts}

    areas: list[FocusArea] = []
    for requirement in requirements:
        verdict = by_id[requirement.id]
        coverage = effective_coverage(verdict)
        importance = requirement.importance or NEUTRAL_IMPORTANCE
        areas.append(
            FocusArea(
                requirement_id=requirement.id,
                coverage=coverage,
                priority=importance * COVERAGE_WEIGHT[coverage],
                preparation_action=PREPARATION_ACTION[coverage],
                reason=verdict.explanation or "No explanation recorded by the matcher.",
            )
        )

    areas.sort(key=lambda area: area.priority, reverse=True)
    return areas

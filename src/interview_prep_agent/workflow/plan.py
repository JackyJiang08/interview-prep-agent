"""Stage 3 - assemble the gap-first focus plan behind the quality gates.

The checks themselves live in :mod:`.gates`, which is where every deterministic
guarantee in the workflow is stated once. This stage applies the plan-level
ones: coverage, so a requirement cannot be dropped or invented between stages,
and traceability, so a match cannot cite evidence that is not in the corpus.

``QualityGateError`` is re-exported here because this module raised it first
and callers still import it from this path.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models import (
    Coverage,
    EvidenceItem,
    FocusPlan,
    PlanItem,
    Requirement,
    RequirementMatch,
    Status,
)
from .gates import QualityGateError, check_plan
from .match import METHOD_NAME


def _note(status: Status, verdict: RequirementMatch) -> str:
    if status is Status.GAP:
        return "No evidence item covers this requirement. Prepare it first."
    cited = ", ".join(match.evidence_id for match in verdict.matches)
    return f"Supported by {cited}."


def build_focus_plan(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    evidence: Sequence[EvidenceItem],
) -> FocusPlan:
    """Combine stage outputs into the final gap-first plan.

    Gaps sort ahead of proven requirements; within each group the source order
    of the posting is preserved so the plan stays readable against the original.

    Raises:
        QualityGateError: If coverage or traceability is violated.
    """
    check_plan(requirements, verdicts, evidence)

    by_id = {verdict.requirement_id: verdict for verdict in verdicts}
    items: list[PlanItem] = []
    for requirement in requirements:
        verdict = by_id[requirement.id]
        items.append(
            PlanItem(
                requirement=requirement,
                status=verdict.status,
                matches=verdict.matches,
                note=_note(verdict.status, verdict),
            )
        )

    items.sort(key=lambda item: (item.status is Status.PROOF,))

    gap_count = sum(1 for item in items if item.status is Status.GAP)
    return FocusPlan(
        coverage=Coverage(
            total=len(items),
            proof=len(items) - gap_count,
            gap=gap_count,
        ),
        items=items,
        method=METHOD_NAME,
    )


__all__ = ["QualityGateError", "build_focus_plan"]

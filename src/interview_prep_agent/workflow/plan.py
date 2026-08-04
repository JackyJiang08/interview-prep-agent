"""Stage 3 - assemble the gap-first focus plan and enforce the quality gates.

The gates are the point of this stage. They are cheap assertions that make the
three failure modes the design cares about loud rather than silent:

* coverage - a requirement was dropped or invented between stages
* traceability - a match cites evidence that is not in the corpus
* grounding - displayed wording drifted from the source posting
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
from .match import METHOD_NAME


class QualityGateError(ValueError):
    """Raised when an artifact violates a stated guarantee of the pipeline."""


def _check_gates(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    evidence: Sequence[EvidenceItem],
) -> None:
    requirement_ids = [item.id for item in requirements]
    verdict_ids = [item.requirement_id for item in verdicts]

    if len(set(requirement_ids)) != len(requirement_ids):
        raise QualityGateError("coverage: duplicate requirement identifiers")

    if set(requirement_ids) != set(verdict_ids):
        missing = set(requirement_ids) - set(verdict_ids)
        invented = set(verdict_ids) - set(requirement_ids)
        raise QualityGateError(
            "coverage: dropped={} invented={}".format(
                sorted(missing) or "none", sorted(invented) or "none"
            )
        )

    known_evidence = {item.id for item in evidence}
    for verdict in verdicts:
        for match in verdict.matches:
            if match.evidence_id not in known_evidence:
                raise QualityGateError(
                    f"traceability: {verdict.requirement_id} cites "
                    f"unknown evidence {match.evidence_id}"
                )
        if verdict.status is Status.PROOF and not verdict.matches:
            raise QualityGateError(
                f"traceability: {verdict.requirement_id} is PROOF with no supporting evidence"
            )


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
    _check_gates(requirements, verdicts, evidence)

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

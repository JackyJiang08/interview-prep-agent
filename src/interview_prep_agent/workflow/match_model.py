"""Stage 2, model-backed - assess coverage through a provider.

The alternative to the lexical scorer in ``match.py``. It reads, so it can
report ``PARTIAL`` — related evidence that misses an important dimension —
which term overlap structurally cannot.

Like model-backed extraction, nothing here trusts the response: it is
validated against the requested schema, converted to the same
``RequirementMatch`` the lexical path emits, and then held to the same
deterministic match gate. A failed call fails the run; there is no canned
substitute (see ``docs/DECISIONS.md``).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..models import (
    CoverageLevel,
    EvidenceItem,
    EvidenceMatch,
    MatchAssessmentList,
    Requirement,
    RequirementMatch,
    Status,
)
from ..providers import ProviderError, StructuredModel

METHOD_NAME = "model-coverage-v1"

MATCHING_INSTRUCTIONS = """\
You match supplied candidate evidence against job requirements.

Return exactly one assessment per requirement_id, in the order the
requirements are listed. For each one:

- coverage FULL: supplied evidence directly supports every important part of
  the requirement.
- coverage PARTIAL: related supplied evidence exists but misses an important
  dimension. Name the missing dimension in the explanation.
- coverage GAP: no supplied evidence supports the requirement. evidence_ids
  must be empty. A gap is a correct and useful answer; report it as one.

Reference only requirement_id and evidence_id values that appear below.
Every FULL or PARTIAL assessment must cite at least one evidence_id. Judge
only the supplied claims: do not infer experience the evidence does not
state, and do not soften a gap into PARTIAL without evidence to cite.
Inventing support is the failure mode this system exists to prevent.

Set confidence between 0 and 1 for how well the cited evidence supports the
coverage you chose. Keep each explanation to one or two sentences, grounded
in the cited evidence.

Return nothing except data conforming to the supplied schema.
"""


def build_matching_prompt(
    requirements: Sequence[Requirement], evidence: Sequence[EvidenceItem]
) -> str:
    """Place both corpora after the instructions, with clear boundaries."""
    requirement_lines = json.dumps(
        [{"requirement_id": item.id, "requirement": item.text} for item in requirements],
        indent=2,
        ensure_ascii=False,
    )
    evidence_lines = json.dumps(
        [
            {
                "evidence_id": item.id,
                "claim": item.summary,
                "skills": item.skills,
                "impact": item.impact,
            }
            for item in evidence
        ],
        indent=2,
        ensure_ascii=False,
    )
    return (
        f"{MATCHING_INSTRUCTIONS}\n"
        "----- REQUIREMENTS -----\n"
        f"{requirement_lines}\n"
        "----- SUPPLIED EVIDENCE -----\n"
        f"{evidence_lines}\n"
    )


def response_schema() -> dict[str, Any]:
    """Return the JSON Schema requested from the provider."""
    return MatchAssessmentList.model_json_schema()


def parse_assessments(payload: Any) -> MatchAssessmentList:
    """Validate a provider response into assessments.

    Raises:
        ProviderError: If the payload does not satisfy the schema.
    """
    try:
        return MatchAssessmentList.model_validate(payload, from_attributes=True)
    except Exception as error:  # noqa: BLE001 - pydantic raises several types
        raise ProviderError(
            f"model response did not match the requested schema: {error}"
        ) from error


def match_evidence_with_model(
    requirements: Sequence[Requirement],
    evidence: Sequence[EvidenceItem],
    model: StructuredModel,
) -> list[RequirementMatch]:
    """Assess every requirement's coverage using a provider.

    The returned verdicts cite evidence by identifier with the assessment's
    confidence as the per-citation score — a provider offers no term overlap
    to report, and none is fabricated. Reference and consistency checking is
    the match gate's job, so both matcher paths face the same one.

    Raises:
        ProviderError: If the call fails or the response cannot be used.
    """
    payload = model.generate_json(build_matching_prompt(requirements, evidence), response_schema())
    assessments = parse_assessments(payload)

    verdicts: list[RequirementMatch] = []
    for item in assessments.assessments:
        verdicts.append(
            RequirementMatch(
                requirement_id=item.requirement_id,
                status=Status.GAP if item.coverage is CoverageLevel.GAP else Status.PROOF,
                matches=[
                    EvidenceMatch(evidence_id=evidence_id, score=item.confidence)
                    for evidence_id in item.evidence_ids
                ],
                method=METHOD_NAME,
                coverage=item.coverage,
                explanation=item.explanation,
                confidence=item.confidence,
            )
        )
    return verdicts

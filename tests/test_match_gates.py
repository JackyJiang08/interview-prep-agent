"""Unit tests for the match gate, on hand-built verdict sets."""

from __future__ import annotations

import pytest

from interview_prep_agent import (
    CoverageLevel,
    EvidenceItem,
    EvidenceMatch,
    Requirement,
    RequirementMatch,
    Status,
    collect_match_errors,
)
from interview_prep_agent.workflow.gates import QualityGateError, check_matches


def requirement(index: int) -> Requirement:
    text = f"Requirement number {index} about analysis"
    return Requirement(
        id=f"REQ-{index:03d}", text=text, normalized=text.casefold(), source_quote=text
    )


def evidence(index: int) -> EvidenceItem:
    return EvidenceItem(id=f"EV-{index:03d}", summary=f"Attested work item {index}")


def verdict(
    index: int,
    coverage: CoverageLevel,
    evidence_ids: tuple[str, ...] = (),
) -> RequirementMatch:
    return RequirementMatch(
        requirement_id=f"REQ-{index:03d}",
        status=Status.GAP if coverage is CoverageLevel.GAP else Status.PROOF,
        matches=[EvidenceMatch(evidence_id=item, score=0.5) for item in evidence_ids],
        method="test",
        coverage=coverage,
        explanation="hand-built verdict",
        confidence=0.5,
    )


REQUIREMENTS = [requirement(1), requirement(2)]
EVIDENCE = [evidence(1), evidence(2)]


def test_a_consistent_set_passes():
    verdicts = [
        verdict(1, CoverageLevel.FULL, ("EV-001",)),
        verdict(2, CoverageLevel.GAP),
    ]
    assert collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE) == []


def test_duplicate_requirement_is_rejected():
    verdicts = [
        verdict(1, CoverageLevel.FULL, ("EV-001",)),
        verdict(1, CoverageLevel.GAP),
        verdict(2, CoverageLevel.GAP),
    ]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "identity: requirements matched more than once: REQ-001" in errors


def test_missing_requirement_is_rejected():
    verdicts = [verdict(1, CoverageLevel.FULL, ("EV-001",))]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "coverage: requirements never matched: REQ-002" in errors


def test_unknown_requirement_is_rejected():
    verdicts = [
        verdict(1, CoverageLevel.GAP),
        verdict(2, CoverageLevel.GAP),
        verdict(9, CoverageLevel.GAP),
    ]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "coverage: verdicts for unknown requirements: REQ-009" in errors


def test_unknown_evidence_id_is_rejected():
    verdicts = [
        verdict(1, CoverageLevel.FULL, ("EV-999",)),
        verdict(2, CoverageLevel.GAP),
    ]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "traceability: REQ-001 cites unknown evidence EV-999" in errors


def test_out_of_order_verdicts_are_rejected():
    verdicts = [
        verdict(2, CoverageLevel.GAP),
        verdict(1, CoverageLevel.FULL, ("EV-001",)),
    ]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "identity: verdicts must follow the requirements' order" in errors


def test_gap_citing_evidence_is_rejected():
    verdicts = [
        verdict(1, CoverageLevel.GAP, ("EV-001",)),
        verdict(2, CoverageLevel.GAP),
    ]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "grounding: REQ-001 is GAP and must not cite evidence" in errors


@pytest.mark.parametrize("coverage", [CoverageLevel.FULL, CoverageLevel.PARTIAL])
def test_supported_coverage_without_citations_is_rejected(coverage):
    verdicts = [verdict(1, coverage), verdict(2, CoverageLevel.GAP)]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert f"grounding: REQ-001 is {coverage.value} with no supporting evidence" in errors


def test_repeated_citation_is_rejected():
    verdicts = [
        verdict(1, CoverageLevel.FULL, ("EV-001", "EV-001")),
        verdict(2, CoverageLevel.GAP),
    ]
    errors = collect_match_errors(REQUIREMENTS, verdicts, EVIDENCE)
    assert "traceability: REQ-001 cites evidence twice" in errors


def test_check_form_raises_with_every_error():
    verdicts = [verdict(1, CoverageLevel.GAP, ("EV-999",))]
    with pytest.raises(QualityGateError, match="never matched.*REQ-002"):
        check_matches(REQUIREMENTS, verdicts, EVIDENCE)

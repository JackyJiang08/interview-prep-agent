"""Tests for the deterministic focus-area assessment and the CLI flag."""

from __future__ import annotations

from interview_prep_agent import (
    CoverageLevel,
    EvidenceMatch,
    Requirement,
    RequirementMatch,
    Status,
    build_focus_areas,
)
from interview_prep_agent.cli import build_parser
from interview_prep_agent.workflow.assess import (
    NEUTRAL_IMPORTANCE,
    PREPARATION_ACTION,
)


def requirement(index: int, importance: int | None = None) -> Requirement:
    text = f"Requirement number {index} about analysis"
    return Requirement(
        id=f"REQ-{index:03d}",
        text=text,
        normalized=text.casefold(),
        source_quote=text,
        importance=importance,
    )


def verdict(index: int, coverage: CoverageLevel, explanation: str = "why") -> RequirementMatch:
    supported = coverage is not CoverageLevel.GAP
    return RequirementMatch(
        requirement_id=f"REQ-{index:03d}",
        status=Status.PROOF if supported else Status.GAP,
        matches=[EvidenceMatch(evidence_id="EV-001", score=0.9)] if supported else [],
        method="test",
        coverage=coverage,
        explanation=explanation,
        confidence=0.9,
    )


def test_priority_is_importance_times_coverage_weight():
    requirements = [requirement(1, importance=5), requirement(2, importance=4)]
    verdicts = [verdict(1, CoverageLevel.PARTIAL), verdict(2, CoverageLevel.GAP)]

    areas = build_focus_areas(requirements, verdicts)

    by_id = {area.requirement_id: area for area in areas}
    assert by_id["REQ-001"].priority == 5 * 2
    assert by_id["REQ-002"].priority == 4 * 3


def test_importance_and_coverage_interact_in_the_ordering():
    # A critical partially-covered requirement outranks a minor gap.
    requirements = [requirement(1, importance=1), requirement(2, importance=5)]
    verdicts = [verdict(1, CoverageLevel.GAP), verdict(2, CoverageLevel.PARTIAL)]

    areas = build_focus_areas(requirements, verdicts)

    assert [area.requirement_id for area in areas] == ["REQ-002", "REQ-001"]
    assert areas[0].priority == 10
    assert areas[1].priority == 3


def test_ties_keep_source_order():
    requirements = [requirement(1, importance=3), requirement(2, importance=3)]
    verdicts = [verdict(1, CoverageLevel.FULL), verdict(2, CoverageLevel.FULL)]

    areas = build_focus_areas(requirements, verdicts)

    assert [area.requirement_id for area in areas] == ["REQ-001", "REQ-002"]


def test_missing_importance_degrades_to_coverage_ordering():
    requirements = [requirement(1), requirement(2), requirement(3)]
    verdicts = [
        verdict(1, CoverageLevel.FULL),
        verdict(2, CoverageLevel.GAP),
        verdict(3, CoverageLevel.PARTIAL),
    ]

    areas = build_focus_areas(requirements, verdicts)

    assert [area.requirement_id for area in areas] == ["REQ-002", "REQ-003", "REQ-001"]
    assert areas[0].priority == NEUTRAL_IMPORTANCE * 3


def test_action_is_fixed_per_coverage_level():
    requirements = [requirement(1), requirement(2), requirement(3)]
    verdicts = [
        verdict(1, CoverageLevel.FULL),
        verdict(2, CoverageLevel.PARTIAL),
        verdict(3, CoverageLevel.GAP),
    ]

    areas = build_focus_areas(requirements, verdicts)

    for area in areas:
        assert area.preparation_action == PREPARATION_ACTION[area.coverage]


def test_reason_carries_the_match_explanation():
    requirements = [requirement(1)]
    verdicts = [verdict(1, CoverageLevel.FULL, explanation="Shared terms with EV-001.")]

    areas = build_focus_areas(requirements, verdicts)

    assert areas[0].reason == "Shared terms with EV-001."


def test_coverage_derives_from_status_when_unset():
    requirements = [requirement(1), requirement(2)]
    verdicts = [
        RequirementMatch(requirement_id="REQ-001", status=Status.GAP, matches=[], method="test"),
        RequirementMatch(
            requirement_id="REQ-002",
            status=Status.PROOF,
            matches=[EvidenceMatch(evidence_id="EV-001", score=0.9)],
            method="test",
        ),
    ]

    areas = build_focus_areas(requirements, verdicts)

    by_id = {area.requirement_id: area for area in areas}
    assert by_id["REQ-001"].coverage is CoverageLevel.GAP
    assert by_id["REQ-002"].coverage is CoverageLevel.FULL


# --- CLI flag ----------------------------------------------------------------


def test_matcher_flag_defaults_to_lexical():
    args = build_parser().parse_args(["match", "--jd", "a", "--evidence", "b"])
    assert args.matcher == "lexical"
    assert args.extractor == "lexical"


def test_matcher_flag_accepts_llm():
    args = build_parser().parse_args(["match", "--jd", "a", "--evidence", "b", "--matcher", "llm"])
    assert args.matcher == "llm"


def test_matcher_flag_rejects_unknown_values(capsys):
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["match", "--jd", "a", "--evidence", "b", "--matcher", "magic"])
    assert excinfo.value.code == 2

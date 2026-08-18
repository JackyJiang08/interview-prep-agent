"""Unit tests for queue selection, the admission gate, and routing."""

from __future__ import annotations

from interview_prep_agent.agent import (
    STOP_BUDGET_EXHAUSTED,
    admission_failure,
    route_after_observation,
    select_next_gap,
    should_admit,
)
from interview_prep_agent.models import (
    ClarificationAssessment,
    CoverageLevel,
    Requirement,
    RequirementMatch,
    Status,
)


def requirement(index: int, importance: int | None) -> Requirement:
    text = f"Requirement number {index} about analysis"
    return Requirement(
        id=f"REQ-{index:03d}",
        text=text,
        normalized=text.casefold(),
        source_quote=text,
        importance=importance,
    )


def verdict(index: int, coverage: CoverageLevel) -> RequirementMatch:
    return RequirementMatch(
        requirement_id=f"REQ-{index:03d}",
        status=Status.GAP if coverage is CoverageLevel.GAP else Status.PROOF,
        matches=[],
        method="test",
        coverage=coverage,
        explanation="hand-built",
        confidence=0.0,
    )


# --- queue selection ----------------------------------------------------------


def test_queue_orders_by_importance_descending():
    requirements = [requirement(1, 3), requirement(2, 5), requirement(3, 4)]
    verdicts = [
        verdict(1, CoverageLevel.GAP),
        verdict(2, CoverageLevel.GAP),
        verdict(3, CoverageLevel.GAP),
    ]

    assert select_next_gap(requirements, verdicts, []).id == "REQ-002"
    assert select_next_gap(requirements, verdicts, ["REQ-002"]).id == "REQ-003"
    assert select_next_gap(requirements, verdicts, ["REQ-002", "REQ-003"]).id == "REQ-001"


def test_queue_breaks_importance_ties_by_identifier():
    requirements = [requirement(2, 5), requirement(1, 5)]
    verdicts = [verdict(2, CoverageLevel.GAP), verdict(1, CoverageLevel.GAP)]
    assert select_next_gap(requirements, verdicts, []).id == "REQ-001"


def test_queue_sorts_missing_importance_last():
    requirements = [requirement(1, None), requirement(2, 1)]
    verdicts = [verdict(1, CoverageLevel.GAP), verdict(2, CoverageLevel.GAP)]
    assert select_next_gap(requirements, verdicts, []).id == "REQ-002"
    assert select_next_gap(requirements, verdicts, ["REQ-002"]).id == "REQ-001"


def test_queue_excludes_processed_and_non_gap():
    requirements = [requirement(1, 5), requirement(2, 5), requirement(3, 5)]
    verdicts = [
        verdict(1, CoverageLevel.FULL),
        verdict(2, CoverageLevel.PARTIAL),
        verdict(3, CoverageLevel.GAP),
    ]
    assert select_next_gap(requirements, verdicts, []).id == "REQ-003"
    # Processed means asked once, not resolved: the gap stays a gap and stays out.
    assert select_next_gap(requirements, verdicts, ["REQ-003"]) is None


def test_queue_ignores_verdicts_for_unknown_requirements():
    verdicts = [verdict(9, CoverageLevel.GAP)]
    assert select_next_gap([requirement(1, 5)], verdicts, []) is None


def test_empty_queue_returns_none():
    assert select_next_gap([], [], []) is None


# --- admission gate -----------------------------------------------------------


def assessment(**updates) -> ClarificationAssessment:
    values = {
        "target_requirement_id": "REQ-002",
        "is_valid": True,
        "relevance_reason": "The answer addresses the requirement directly.",
        "specificity_reason": "The answer names concrete work and a result.",
        "accepted_claim": "Designed controlled experiments for product decisions.",
    }
    values.update(updates)
    return ClarificationAssessment.model_validate(values)


LONG_ANSWER = "I designed controlled experiments for product decisions all year."


def test_a_short_answer_is_rejected_before_any_model_judgment():
    failure = admission_failure("I wrote SQL.", assessment(), "REQ-002", 24)
    assert failure == "admission: the answer must contain at least 24 characters"


def test_a_redirected_assessment_is_rejected():
    failure = admission_failure(
        LONG_ANSWER, assessment(target_requirement_id="REQ-003"), "REQ-002", 24
    )
    assert failure == (
        "admission: the assessment targeted REQ-003, not the requirement asked (REQ-002)"
    )


def test_an_invalid_assessment_is_rejected_with_its_reasons():
    failure = admission_failure(
        LONG_ANSWER, assessment(is_valid=False, accepted_claim=None), "REQ-002", 24
    )
    assert failure.startswith("admission: the assessment rejected the answer")


def test_a_valid_assessment_without_a_claim_is_rejected():
    failure = admission_failure(LONG_ANSWER, assessment(accepted_claim=None), "REQ-002", 24)
    assert failure == ("admission: a valid assessment must carry a non-empty accepted claim")


def test_a_whitespace_claim_is_rejected():
    failure = admission_failure(LONG_ANSWER, assessment(accepted_claim="   "), "REQ-002", 24)
    assert failure is not None


def test_every_gate_passing_admits():
    assert admission_failure(LONG_ANSWER, assessment(), "REQ-002", 24) is None
    assert should_admit(LONG_ANSWER, assessment(), "REQ-002", 24) is True


def test_the_length_floor_is_configurable():
    assert should_admit("Short but fine.", assessment(), "REQ-002", 5) is True
    assert should_admit("Short but fine.", assessment(), "REQ-002", 24) is False


# --- routing ------------------------------------------------------------------


def test_an_invalid_initial_package_routes_to_invalid():
    assert route_after_observation({"package_valid": False}) == "invalid"


def test_a_current_gap_with_budget_routes_to_ask():
    state = {
        "package_valid": True,
        "current_gap": requirement(1, 5),
        "question_budget_left": True,
    }
    assert route_after_observation(state) == "ask"


def test_an_exhausted_question_budget_routes_to_final_generation():
    state = {
        "package_valid": True,
        "current_gap": requirement(1, 5),
        "question_budget_left": False,
    }
    assert route_after_observation(state) == "generate_final"


def test_an_empty_queue_routes_to_final_generation():
    state = {"package_valid": True, "current_gap": None, "question_budget_left": True}
    assert route_after_observation(state) == "generate_final"


def test_an_exhausted_action_budget_routes_to_invalid():
    state = {
        "package_valid": True,
        "current_gap": requirement(1, 5),
        "question_budget_left": True,
        "stop_reason": STOP_BUDGET_EXHAUSTED,
    }
    assert route_after_observation(state) == "invalid"

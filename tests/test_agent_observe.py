"""Unit tests for observation derivation and code-owned authorization."""

from __future__ import annotations

from interview_prep_agent.agent import authorize, derive_observation
from interview_prep_agent.models import (
    AgentAction,
    AgentDecision,
    AgentObservation,
    Clarification,
    CoverageLevel,
    HighPriorityGap,
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


def gap_verdict(index: int) -> RequirementMatch:
    return RequirementMatch(
        requirement_id=f"REQ-{index:03d}",
        status=Status.GAP,
        matches=[],
        method="test",
        coverage=CoverageLevel.GAP,
        explanation="Nothing supplied covers this.",
        confidence=0.0,
    )


def clarification(index: int) -> Clarification:
    return Clarification(
        requirement_id=f"REQ-{index:03d}",
        question="What did you actually do here?",
        answer="I ran the controlled experiment end to end.",
    )


def observe(state: dict, actions: int = 4, questions: int = 1) -> AgentObservation:
    return derive_observation(state, actions, questions)


# --- gap eligibility and ordering --------------------------------------------


def test_importance_four_gap_is_eligible():
    observation = observe({"requirements": [requirement(1, 4)], "matches": [gap_verdict(1)]})
    assert observation.high_priority_gap_ids == ["REQ-001"]
    assert observation.high_priority_gaps[0].importance == 4


def test_importance_three_gap_is_excluded():
    observation = observe({"requirements": [requirement(1, 3)], "matches": [gap_verdict(1)]})
    assert observation.high_priority_gap_ids == []


def test_missing_importance_never_qualifies():
    observation = observe({"requirements": [requirement(1, None)], "matches": [gap_verdict(1)]})
    assert observation.high_priority_gap_ids == []


def test_gaps_sort_by_importance_then_identifier():
    state = {
        "requirements": [requirement(1, 4), requirement(2, 5), requirement(3, 5)],
        "matches": [gap_verdict(1), gap_verdict(2), gap_verdict(3)],
    }
    observation = observe(state)
    assert observation.high_priority_gap_ids == ["REQ-002", "REQ-003", "REQ-001"]


# --- allowed-action derivation ------------------------------------------------


def test_nothing_generated_allows_only_generate():
    observation = observe({})
    assert observation.allowed_actions == [AgentAction.GENERATE_PREP_PACKAGE]


def test_fresh_clarification_allows_only_generate():
    state = {
        "requirements": [requirement(1, 5)],
        "matches": [gap_verdict(1)],
        "package_generated": True,
        "package_valid": True,
        "last_action": AgentAction.ASK_USER,
        "clarifications": [clarification(1)],
        "asked_requirement_ids": ["REQ-001"],
    }
    observation = observe(state)
    assert observation.allowed_actions == [AgentAction.GENERATE_PREP_PACKAGE]
    assert observation.latest_clarification.startswith("I ran")


def test_unasked_gap_with_question_budget_allows_ask():
    state = {
        "requirements": [requirement(1, 5)],
        "matches": [gap_verdict(1)],
        "package_generated": True,
        "package_valid": True,
        "last_action": AgentAction.GENERATE_PREP_PACKAGE,
    }
    observation = observe(state)
    assert observation.allowed_actions == [AgentAction.ASK_USER]


def test_valid_package_with_nothing_to_ask_allows_finish():
    state = {
        "requirements": [requirement(1, 5)],
        "matches": [gap_verdict(1)],
        "package_generated": True,
        "package_valid": True,
        "asked_requirement_ids": ["REQ-001"],
        "last_action": AgentAction.GENERATE_PREP_PACKAGE,
    }
    observation = observe(state)
    assert observation.allowed_actions == [AgentAction.FINISH]


def test_invalid_package_falls_back_to_generate():
    state = {
        "package_generated": True,
        "package_valid": False,
        "last_action": AgentAction.GENERATE_PREP_PACKAGE,
    }
    observation = observe(state)
    assert observation.allowed_actions == [AgentAction.GENERATE_PREP_PACKAGE]


def test_exhausted_budget_allows_nothing():
    observation = observe({"action_count": 4})
    assert observation.allowed_actions == []
    assert observation.steps_remaining == 0


def test_question_budget_zero_never_allows_ask():
    state = {
        "requirements": [requirement(1, 5)],
        "matches": [gap_verdict(1)],
        "package_generated": True,
        "package_valid": True,
        "last_action": AgentAction.GENERATE_PREP_PACKAGE,
    }
    observation = observe(state, questions=0)
    assert observation.allowed_actions == [AgentAction.FINISH]


def test_budget_arithmetic():
    assert observe({"action_count": 0}).steps_remaining == 4
    assert observe({"action_count": 3}).steps_remaining == 1
    assert observe({"action_count": 9}).steps_remaining == 0
    assert observe({"action_count": 1}, actions=2).steps_remaining == 1


# --- authorization gates ------------------------------------------------------


def observation_for_auth(**updates) -> AgentObservation:
    values = {
        "package_generated": True,
        "package_valid": True,
        "high_priority_gap_ids": ["REQ-001"],
        "high_priority_gaps": [
            HighPriorityGap(
                requirement_id="REQ-001",
                text="Requirement number 1 about analysis",
                importance=5,
                explanation="Nothing supplied covers this.",
            )
        ],
        "asked_requirement_ids": [],
        "allowed_actions": [AgentAction.ASK_USER],
        "last_action": AgentAction.GENERATE_PREP_PACKAGE,
        "steps_remaining": 3,
    }
    values.update(updates)
    return AgentObservation.model_validate(values)


def decision(action: AgentAction, **updates) -> AgentDecision:
    values = {"next_action": action, "reason_summary": "The next bounded action."}
    values.update(updates)
    return AgentDecision.model_validate(values)


def test_exhausted_budget_is_rejected():
    route, error = authorize(
        decision(AgentAction.GENERATE_PREP_PACKAGE),
        observation_for_auth(steps_remaining=0, allowed_actions=[]),
        1,
    )
    assert route == "invalid"
    assert "budget is exhausted" in error


def test_action_outside_the_allowed_set_is_rejected():
    route, error = authorize(
        decision(AgentAction.FINISH),
        observation_for_auth(allowed_actions=[AgentAction.ASK_USER]),
        1,
    )
    assert route == "invalid"
    assert "FINISH is not in the allowed set (ASK_USER)" in error


def test_ask_without_question_or_target_is_rejected():
    route, error = authorize(decision(AgentAction.ASK_USER), observation_for_auth(), 1)
    assert route == "invalid"
    assert "requires a target requirement and a question" in error


def test_ask_targeting_a_non_gap_is_rejected():
    route, error = authorize(
        decision(
            AgentAction.ASK_USER,
            target_requirement_id="REQ-009",
            question="What was the outcome?",
        ),
        observation_for_auth(),
        1,
    )
    assert route == "invalid"
    assert "REQ-009 is not an eligible high-priority gap" in error


def test_ask_repeating_a_requirement_is_rejected():
    route, error = authorize(
        decision(
            AgentAction.ASK_USER,
            target_requirement_id="REQ-001",
            question="What was the outcome?",
        ),
        observation_for_auth(asked_requirement_ids=["REQ-001"]),
        2,
    )
    assert route == "invalid"
    assert "REQ-001 has already been asked" in error


def test_ask_beyond_the_question_budget_is_rejected():
    route, error = authorize(
        decision(
            AgentAction.ASK_USER,
            target_requirement_id="REQ-001",
            question="What was the outcome?",
        ),
        observation_for_auth(asked_requirement_ids=["REQ-002"]),
        1,
    )
    assert route == "invalid"
    assert "at most 1 question(s) per run" in error


def test_finish_without_a_valid_package_is_rejected():
    route, error = authorize(
        decision(AgentAction.FINISH),
        observation_for_auth(package_valid=False, allowed_actions=[AgentAction.FINISH]),
        1,
    )
    assert route == "invalid"
    assert "FINISH requires a valid package" in error


def test_finish_with_an_eligible_unasked_gap_is_rejected():
    route, error = authorize(
        decision(AgentAction.FINISH),
        observation_for_auth(allowed_actions=[AgentAction.FINISH]),
        1,
    )
    assert route == "invalid"
    assert "no eligible unasked high-priority gap" in error


def test_valid_proposals_route_to_their_capabilities():
    assert authorize(
        decision(AgentAction.GENERATE_PREP_PACKAGE),
        observation_for_auth(allowed_actions=[AgentAction.GENERATE_PREP_PACKAGE]),
        1,
    ) == ("generate", None)
    assert authorize(
        decision(
            AgentAction.ASK_USER,
            target_requirement_id="REQ-001",
            question="What was the outcome?",
        ),
        observation_for_auth(),
        1,
    ) == ("ask", None)
    assert authorize(
        decision(AgentAction.FINISH),
        observation_for_auth(
            allowed_actions=[AgentAction.FINISH], asked_requirement_ids=["REQ-001"]
        ),
        2,
    ) == ("finish", None)

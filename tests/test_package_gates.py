"""Hand-built failing cases for the strategy, question and package gates,
plus the resume reader."""

from __future__ import annotations

import pytest

from interview_prep_agent import (
    CoverageLevel,
    EvidenceItem,
    EvidenceMatch,
    FocusArea,
    InterviewStrategy,
    MockQuestion,
    Requirement,
    RequirementMatch,
    RiskItem,
    Status,
    StoryPlan,
    StrategyItem,
)
from interview_prep_agent.corpus import CorpusError, parse_evidence_markdown
from interview_prep_agent.workflow.gates import (
    QualityGateError,
    check_strategy,
    collect_package_errors,
    collect_question_errors,
    collect_strategy_errors,
)

POSTING = "Requirements\n- Strong SQL and Python analysis\n- Kubernetes operations\n"


def requirement(index: int, text: str) -> Requirement:
    return Requirement(
        id=f"REQ-{index:03d}", text=text, normalized=text.casefold(), source_quote=text
    )


REQUIREMENTS = [
    requirement(1, "Strong SQL and Python analysis"),
    requirement(2, "Kubernetes operations"),
]
EVIDENCE = [EvidenceItem(id="EV-001", summary="SQL and Python analysis at scale")]

VERDICTS = [
    RequirementMatch(
        requirement_id="REQ-001",
        status=Status.PROOF,
        matches=[EvidenceMatch(evidence_id="EV-001", score=0.9)],
        method="test",
        coverage=CoverageLevel.FULL,
        explanation="Direct overlap.",
        confidence=0.9,
    ),
    RequirementMatch(
        requirement_id="REQ-002",
        status=Status.GAP,
        matches=[],
        method="test",
        coverage=CoverageLevel.GAP,
        explanation="Nothing supplied.",
        confidence=0.0,
    ),
]

FOCUS_AREAS = [
    FocusArea(
        requirement_id="REQ-002",
        coverage=CoverageLevel.GAP,
        priority=3,
        preparation_action="Prepare an honest gap response and a concrete learning plan.",
        reason="Nothing supplied.",
    ),
    FocusArea(
        requirement_id="REQ-001",
        coverage=CoverageLevel.FULL,
        priority=1,
        preparation_action="Prepare a concise story that proves this strength.",
        reason="Direct overlap.",
    ),
]


def strategy(
    risk_ids: tuple[str, ...] = ("REQ-002",),
    story_evidence: tuple[str, ...] = ("EV-001",),
    priority_id: str = "REQ-001",
) -> InterviewStrategy:
    return InterviewStrategy(
        top_priorities=[
            StrategyItem(
                requirement_id=priority_id,
                evidence_ids=list(story_evidence) if priority_id == "REQ-001" else [],
                preparation_theme="Lead with proven analysis",
                rationale="Strongest supported area.",
            )
        ],
        positioning_statement="An analyst with attested SQL and Python depth.",
        stories_to_prepare=[
            StoryPlan(
                requirement_id="REQ-001",
                evidence_ids=list(story_evidence),
                story_to_prepare="The analysis and its outcome.",
            )
        ],
        risks_to_address=[
            RiskItem(
                requirement_id=identifier,
                risk="May be probed without support.",
                mitigation="Prepare an honest answer.",
            )
            for identifier in risk_ids
        ],
    )


def question_set(count: int, requirement_id: str = "REQ-001") -> list[MockQuestion]:
    return [
        MockQuestion(
            question=f"Practice question number {index}?",
            requirement_id=requirement_id,
            capability_tested="analysis",
            evidence_ids=["EV-001"] if requirement_id == "REQ-001" else [],
            follow_up_probe="What changed?",
            answer_outline=["Context.", "Outcome."],
        )
        for index in range(1, count + 1)
    ]


# --- strategy gate -----------------------------------------------------------


def test_a_consistent_strategy_passes():
    errors = collect_strategy_errors(REQUIREMENTS, VERDICTS, FOCUS_AREAS, strategy())
    assert errors == []


def test_unknown_requirement_reference_is_rejected():
    bad = strategy(priority_id="REQ-999")
    errors = collect_strategy_errors(REQUIREMENTS, VERDICTS, FOCUS_AREAS, bad)
    assert "traceability: strategy item references unknown requirement REQ-999" in errors


def test_evidence_outside_the_match_is_rejected():
    bad = strategy(story_evidence=("EV-777",))
    errors = collect_strategy_errors(REQUIREMENTS, VERDICTS, FOCUS_AREAS, bad)
    assert any("cites evidence not matched" in item and "EV-777" in item for item in errors)


def test_gap_focus_area_missing_from_risks_is_rejected():
    bad = strategy(risk_ids=())
    errors = collect_strategy_errors(REQUIREMENTS, VERDICTS, FOCUS_AREAS, bad)
    assert "coverage: gap focus area REQ-002 does not appear in risks_to_address" in errors


def test_check_strategy_raises():
    with pytest.raises(QualityGateError, match="risks_to_address"):
        check_strategy(REQUIREMENTS, VERDICTS, FOCUS_AREAS, strategy(risk_ids=()))


# --- question gate -----------------------------------------------------------


def test_enough_grounded_questions_pass():
    assert collect_question_errors(REQUIREMENTS, VERDICTS, question_set(8)) == []


def test_below_the_question_floor_is_rejected():
    errors = collect_question_errors(REQUIREMENTS, VERDICTS, question_set(7))
    assert errors[0].startswith("coverage: expected at least 8 practice questions")


def test_a_question_citing_an_unknown_requirement_is_rejected():
    questions = question_set(7) + question_set(1, requirement_id="REQ-404")
    errors = collect_question_errors(REQUIREMENTS, VERDICTS, questions)
    assert "traceability: question references unknown requirement REQ-404" in errors


def test_a_gap_question_citing_evidence_is_rejected():
    questions = question_set(7)
    questions.append(
        MockQuestion(
            question="How would you close this gap?",
            requirement_id="REQ-002",
            capability_tested="honesty",
            evidence_ids=["EV-001"],
            follow_up_probe="What is the plan?",
            answer_outline=["Acknowledge.", "Plan."],
        )
    )
    errors = collect_question_errors(REQUIREMENTS, VERDICTS, questions)
    assert "grounding: question for REQ-002 must not cite evidence for a gap" in errors


# --- package gate ------------------------------------------------------------


def test_a_complete_package_passes():
    errors = collect_package_errors(
        POSTING, EVIDENCE, REQUIREMENTS, VERDICTS, FOCUS_AREAS, strategy(), question_set(8)
    )
    assert errors == []


def test_a_missing_strategy_is_rejected():
    errors = collect_package_errors(
        POSTING, EVIDENCE, REQUIREMENTS, VERDICTS, FOCUS_AREAS, None, question_set(8)
    )
    assert "coverage: the package has no strategy" in errors


def test_a_missing_focus_area_is_rejected():
    errors = collect_package_errors(
        POSTING, EVIDENCE, REQUIREMENTS, VERDICTS, FOCUS_AREAS[:1], strategy(), question_set(8)
    )
    assert "coverage: no focus area for REQ-001" in errors


def test_focus_coverage_disagreeing_with_the_verdict_is_rejected():
    disagreeing = [
        FOCUS_AREAS[0],
        FOCUS_AREAS[1].model_copy(update={"coverage": CoverageLevel.PARTIAL}),
    ]
    errors = collect_package_errors(
        POSTING, EVIDENCE, REQUIREMENTS, VERDICTS, disagreeing, strategy(), question_set(8)
    )
    assert "identity: focus area REQ-001 coverage disagrees with the match verdict" in errors


def test_a_verdict_without_explicit_coverage_is_rejected():
    verdicts = [
        VERDICTS[0].model_copy(update={"coverage": None}),
        VERDICTS[1],
    ]
    errors = collect_package_errors(
        POSTING, EVIDENCE, REQUIREMENTS, verdicts, FOCUS_AREAS, strategy(), question_set(8)
    )
    assert "coverage: REQ-001 carries no explicit coverage level" in errors


# --- resume reader -----------------------------------------------------------


def test_resume_bullets_become_sequential_stable_identifiers():
    resume = (
        "## Work\n\n- First achievement here\n- Second achievement here\n\n"
        "## Other\n\n- Third achievement here\n"
    )
    items = parse_evidence_markdown(resume)
    assert [item.id for item in items] == ["EV-001", "EV-002", "EV-003"]
    assert items[0].source == "Work"
    assert items[2].source == "Other"


def test_wrapped_bullet_lines_join_into_one_item():
    resume = "## Work\n\n- Led analysis across\n  forty million events\n"
    items = parse_evidence_markdown(resume)
    assert len(items) == 1
    assert items[0].summary == "Led analysis across forty million events"


def test_prose_without_bullets_is_still_evidence():
    items = parse_evidence_markdown("# Just a title\n\nProse with no bullets at all.\n")
    assert [item.summary for item in items] == ["Prose with no bullets at all."]
    assert items[0].source == "Just a title"


def test_an_empty_resume_is_rejected():
    with pytest.raises(CorpusError, match="no readable content"):
        parse_evidence_markdown("# Just a title\n\nPage 1 of 1\n---\n")

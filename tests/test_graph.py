"""Graph-level tests: both branches, and the predicate that chooses between them."""

from __future__ import annotations

from interview_prep_agent import Requirement, build_workflow
from interview_prep_agent.workflow.graph import route_after_validation
from interview_prep_agent.workflow.pipeline import run_workflow


def ungrounded_extractor(_job_description: str) -> list[Requirement]:
    """Stand in for an extractor that invents a requirement."""
    return [
        Requirement(
            id="REQ-001",
            text="Ten years of robotics leadership",
            normalized="ten years of robotics leadership",
            source_quote="Ten years of robotics leadership",
        )
    ]


def empty_extractor(_job_description: str) -> list[Requirement]:
    return []


def test_valid_extraction_reaches_a_plan(sample_job_description, sample_evidence):
    state = run_workflow(sample_job_description, sample_evidence)

    assert state["requirements_valid"] is True
    assert state["validation_errors"] == []
    assert state["status"] == "complete"
    assert state["plan"] is not None
    assert state["plan"].coverage.total == len(state["requirements"])


def test_invalid_extraction_routes_to_report_errors(sample_job_description, sample_evidence):
    workflow = build_workflow(extractor=ungrounded_extractor)

    state = workflow.invoke(
        {"job_description": sample_job_description, "evidence": sample_evidence}
    )

    assert state["requirements_valid"] is False
    assert state["status"] == "invalid"
    assert state["plan"] is None
    assert state["validation_errors"] == [
        "grounding: REQ-001 source quote does not appear in the job description"
    ]


def test_the_invalid_branch_never_reaches_matching(sample_job_description, sample_evidence):
    workflow = build_workflow(extractor=ungrounded_extractor)

    state = workflow.invoke(
        {"job_description": sample_job_description, "evidence": sample_evidence}
    )

    assert "matches" not in state or not state["matches"]


def test_empty_extraction_is_reported_not_silently_accepted(
    sample_job_description, sample_evidence
):
    workflow = build_workflow(extractor=empty_extractor, min_requirements=1)

    state = workflow.invoke(
        {"job_description": sample_job_description, "evidence": sample_evidence}
    )

    assert state["status"] == "invalid"
    assert any("coverage: expected between" in e for e in state["validation_errors"])


def test_route_is_a_pure_function_of_the_validation_flag():
    assert route_after_validation({"requirements_valid": True}) == "valid"
    assert route_after_validation({"requirements_valid": False}) == "invalid"
    assert route_after_validation({}) == "invalid"


def test_the_branch_set_is_closed():
    """Only the two wired targets are reachable, whatever the state contains."""
    noisy = {"requirements_valid": True, "status": "anything", "plan": None}
    assert route_after_validation(noisy) in {"valid", "invalid"}

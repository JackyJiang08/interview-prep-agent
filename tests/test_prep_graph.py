"""Graph-level tests for the full preparation workflow, seam mocked.

The fake provider dispatches on the requested response schema, so one
instance serves the strategy and question nodes without any network.
"""

from __future__ import annotations

import json
from typing import Any

from interview_prep_agent import StructuredModel
from interview_prep_agent.workflow.graph import build_prep_workflow, route_after_package
from interview_prep_agent.workflow.pipeline import run_prep

JOB_DESCRIPTION = """Requirements
- Strong SQL and Python for analysis on large datasets
- Experience designing and interpreting A/B tests
"""

RESUME = """# Candidate

## Experience

- Owned funnel analysis in SQL and Python on large datasets
- Presented findings to product partners weekly
"""

# The lexical defaults over these inputs yield REQ-001 FULL (EV-001 cited)
# and REQ-002 GAP.


def strategy_payload() -> dict[str, Any]:
    return {
        "top_priorities": [
            {
                "requirement_id": "REQ-002",
                "evidence_ids": [],
                "preparation_theme": "Close the experimentation gap",
                "rationale": "No supplied evidence covers testing.",
            }
        ],
        "positioning_statement": "An analyst with proven SQL and Python depth.",
        "stories_to_prepare": [
            {
                "requirement_id": "REQ-001",
                "evidence_ids": ["EV-001"],
                "story_to_prepare": "The funnel analysis and what it changed.",
            }
        ],
        "risks_to_address": [
            {
                "requirement_id": "REQ-002",
                "risk": "No experimentation evidence to point at.",
                "mitigation": "Prepare an honest answer and a learning plan.",
            }
        ],
    }


def question(index: int, requirement_id: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "question": f"Practice question number {index}?",
        "requirement_id": requirement_id,
        "capability_tested": "analysis",
        "evidence_ids": evidence_ids,
        "follow_up_probe": "What changed as a result?",
        "answer_outline": ["State the context.", "State the outcome."],
    }


def questions_payload(count: int = 8) -> dict[str, Any]:
    return {
        "mock_questions": [
            question(index, "REQ-001", ["EV-001"]) if index % 2 else question(index, "REQ-002", [])
            for index in range(1, count + 1)
        ]
    }


class DispatchingModel(StructuredModel):
    """Return the payload matching whichever schema was requested."""

    def __init__(self, question_count: int = 8) -> None:
        self.question_count = question_count
        self.schemas_requested: list[str] = []

    @property
    def name(self) -> str:
        return "dispatching"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        properties = set(response_schema.get("properties", {}))
        if "top_priorities" in properties:
            self.schemas_requested.append("strategy")
            return strategy_payload()
        if "mock_questions" in properties:
            self.schemas_requested.append("questions")
            return questions_payload(self.question_count)
        raise AssertionError(f"unexpected schema: {sorted(properties)}")


def invoke(model: StructuredModel):
    workflow = build_prep_workflow(model=model)
    return workflow.invoke(
        {
            "job_description": JOB_DESCRIPTION,
            "evidence_source": RESUME,
            "evidence_format": "markdown",
        }
    )


def test_a_valid_run_reaches_a_package():
    model = DispatchingModel()

    state = invoke(model)

    assert state["package_valid"] is True
    assert state["validation_errors"] == []
    assert state["status"] == "complete"
    package = state["prep_package"]
    assert package is not None
    assert len(package.mock_questions) == 8
    assert model.schemas_requested == ["strategy", "questions"]


def test_too_few_questions_routes_to_report_errors():
    model = DispatchingModel(question_count=7)

    state = invoke(model)

    assert state["package_valid"] is False
    assert state["status"] == "invalid"
    assert state["prep_package"] is None
    assert any("at least 8 practice questions" in item for item in state["validation_errors"])


def test_route_is_a_pure_function_of_the_package_flag():
    assert route_after_package({"package_valid": True}) == "valid"
    assert route_after_package({"package_valid": False}) == "invalid"
    assert route_after_package({}) == "invalid"


def test_run_prep_writes_artifacts_only_for_what_exists(tmp_path):
    state = run_prep(
        JOB_DESCRIPTION,
        RESUME,
        "markdown",
        output_dir=tmp_path,
        model=DispatchingModel(),
    )

    assert state["package_valid"] is True
    for name in (
        "requirements.json",
        "matches.json",
        "focus_areas.json",
        "strategy.json",
        "questions.json",
        "prep_package.json",
    ):
        assert (tmp_path / name).is_file()
        json.loads((tmp_path / name).read_text(encoding="utf-8"))


def test_an_invalid_run_writes_no_package_artifact(tmp_path):
    state = run_prep(
        JOB_DESCRIPTION,
        RESUME,
        "markdown",
        output_dir=tmp_path,
        model=DispatchingModel(question_count=6),
    )

    assert state["package_valid"] is False
    assert not (tmp_path / "prep_package.json").exists()
    assert (tmp_path / "questions.json").is_file()

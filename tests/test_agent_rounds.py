"""Round context: parsing, threading into preparation, and the invariant.

The invariant under test: round context changes what to emphasize — the
strategy and question prompts — never what the candidate can claim, so
extraction and matching results are identical with and without it.
"""

from __future__ import annotations

from typing import Any

from interview_prep_agent import StructuredModel
from interview_prep_agent.models import InterviewRound
from interview_prep_agent.workflow.graph import build_prep_workflow
from interview_prep_agent.workflow.questions import build_question_prompt
from interview_prep_agent.workflow.strategy import build_strategy_prompt

JOB_DESCRIPTION = """Requirements
- Strong SQL and Python for analysis on large datasets
- Experience designing and interpreting A/B tests
"""

EVIDENCE_YAML = """\
- id: EV-001
  summary: Owned SQL and Python analysis on large datasets
  skills: [sql, python, analysis]
"""

ROUND = InterviewRound(
    round_type="technical screen",
    interviewer_roles=["engineering manager"],
    focus=["experiment design"],
)


def question_payload(index: int, requirement_id: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "question": f"Practice question number {index}?",
        "requirement_id": requirement_id,
        "capability_tested": "analysis",
        "evidence_ids": evidence_ids,
        "follow_up_probe": "What changed as a result?",
        "answer_outline": ["State the context.", "State the outcome."],
    }


class RecordingWorkflowProvider(StructuredModel):
    """Serve minimal valid strategy and question payloads, recording prompts."""

    def __init__(self) -> None:
        self.strategy_prompts: list[str] = []
        self.question_prompts: list[str] = []

    @property
    def name(self) -> str:
        return "recording"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        properties = set(response_schema.get("properties", {}))
        if "top_priorities" in properties:
            self.strategy_prompts.append(prompt)
            return {
                "top_priorities": [
                    {
                        "requirement_id": "REQ-001",
                        "evidence_ids": ["EV-001"],
                        "preparation_theme": "Lead with proven analysis",
                        "rationale": "Strongest supported requirement.",
                    }
                ],
                "positioning_statement": "An analyst with attested depth.",
                "stories_to_prepare": [
                    {
                        "requirement_id": "REQ-001",
                        "evidence_ids": ["EV-001"],
                        "story_to_prepare": "The analysis and what it changed.",
                    }
                ],
                "risks_to_address": [
                    {
                        "requirement_id": "REQ-002",
                        "risk": "May be probed without supporting evidence.",
                        "mitigation": "Prepare an honest answer.",
                    }
                ],
            }
        if "mock_questions" in properties:
            self.question_prompts.append(prompt)
            return {
                "mock_questions": [
                    question_payload(
                        index,
                        "REQ-001" if index % 2 else "REQ-002",
                        ["EV-001"] if index % 2 else [],
                    )
                    for index in range(1, 9)
                ]
            }
        raise AssertionError(f"unexpected schema: {sorted(properties)}")


def invoke_workflow(round_context: InterviewRound | None):
    provider = RecordingWorkflowProvider()
    workflow = build_prep_workflow(model=provider)
    state = workflow.invoke(
        {
            "job_description": JOB_DESCRIPTION,
            "evidence_source": EVIDENCE_YAML,
            "evidence_format": "corpus",
            "round_context": round_context,
        }
    )
    return state, provider


def test_round_threads_into_both_preparation_prompts():
    _, provider = invoke_workflow(ROUND)

    for prompt in (provider.strategy_prompts[0], provider.question_prompts[0]):
        assert "----- INTERVIEW ROUND -----" in prompt
        assert "technical screen" in prompt
        assert "engineering manager" in prompt
        assert "experiment design" in prompt


def test_absent_round_means_no_round_section():
    _, provider = invoke_workflow(None)

    assert "----- INTERVIEW ROUND -----" not in provider.strategy_prompts[0]
    assert "----- INTERVIEW ROUND -----" not in provider.question_prompts[0]


def test_matches_are_identical_with_and_without_a_round():
    with_round, _ = invoke_workflow(ROUND)
    without_round, _ = invoke_workflow(None)

    assert [v.model_dump() for v in with_round["matches"]] == [
        v.model_dump() for v in without_round["matches"]
    ]
    assert [r.model_dump() for r in with_round["requirements"]] == [
        r.model_dump() for r in without_round["requirements"]
    ]


def test_prompt_builders_render_the_round_section_directly():
    strategy_prompt = build_strategy_prompt([], [], [], ROUND)
    question_prompt = build_question_prompt(
        [],
        [],
        strategy=__import__("interview_prep_agent").models.InterviewStrategy(
            positioning_statement="x"
        ),
        round_context=ROUND,
    )
    assert "technical screen" in strategy_prompt
    assert "technical screen" in question_prompt
    assert "----- INTERVIEW ROUND -----" not in build_strategy_prompt([], [], [], None)

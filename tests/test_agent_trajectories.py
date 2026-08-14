"""End-to-end trajectories through the decision loop, fully offline.

One scripted provider serves every model stage, dispatching on the requested
response schema: decisions are consumed in order, and the workflow's strategy
and question stages are answered from the current requirement set.
"""

from __future__ import annotations

from typing import Any

from interview_prep_agent import Requirement, StructuredModel
from interview_prep_agent.agent import (
    STOP_BUDGET_EXHAUSTED,
    STOP_INVALID_DECISION,
    STOP_VALID_PACKAGE,
    run_agent,
)
from interview_prep_agent.config import Settings

JOB_DESCRIPTION = """Requirements
- Strong SQL and Python for analysis on large datasets
- Designing controlled experiments for product decisions
"""

EVIDENCE_YAML = """\
- id: EV-001
  summary: Owned SQL and Python analysis on large datasets
  skills: [sql, python, analysis]
"""

ANSWER = (
    "I spent a year designing controlled experiments for product decisions, "
    "owning the full analysis."
)


def scripted_extractor(job_description: str) -> list[Requirement]:
    """Deterministic extraction with importance set, grounded in the posting."""
    texts = [
        ("Strong SQL and Python for analysis on large datasets", 3),
        ("Designing controlled experiments for product decisions", 5),
    ]
    return [
        Requirement(
            id=f"REQ-{index:03d}",
            text=text,
            normalized=text.casefold(),
            source_quote=text,
            importance=importance,
        )
        for index, (text, importance) in enumerate(texts, start=1)
    ]


def question_payload(index: int, requirement_id: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "question": f"Practice question number {index}?",
        "requirement_id": requirement_id,
        "capability_tested": "analysis",
        "evidence_ids": evidence_ids,
        "follow_up_probe": "What changed as a result?",
        "answer_outline": ["State the context.", "State the outcome."],
    }


class ScriptedProvider(StructuredModel):
    """Serve decisions from a script; answer workflow stages from state shown."""

    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = list(decisions)
        self.decision_prompts: list[str] = []

    @property
    def name(self) -> str:
        return "scripted"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        properties = set(response_schema.get("properties", {}))
        if "next_action" in properties:
            self.decision_prompts.append(prompt)
            if not self.decisions:
                raise AssertionError("the script ran out of decisions")
            return self.decisions.pop(0)
        if "top_priorities" in properties:
            return self._strategy(prompt)
        if "mock_questions" in properties:
            return self._questions(prompt)
        raise AssertionError(f"unexpected schema: {sorted(properties)}")

    def _gap_ids(self, prompt: str) -> list[str]:
        # The matches block in the prompt names each requirement's coverage.
        return [
            line.split('"requirement_id": "')[1].split('"')[0]
            for line in _coverage_lines(prompt, "GAP")
        ]

    def _strategy(self, prompt: str) -> dict[str, Any]:
        gap_ids = self._gap_ids(prompt)
        supported = "REQ-001"
        return {
            "top_priorities": [
                {
                    "requirement_id": supported,
                    "evidence_ids": ["EV-001"],
                    "preparation_theme": "Lead with proven analysis",
                    "rationale": "Strongest supported requirement.",
                }
            ],
            "positioning_statement": "An analyst with attested SQL and Python depth.",
            "stories_to_prepare": [
                {
                    "requirement_id": supported,
                    "evidence_ids": ["EV-001"],
                    "story_to_prepare": "The analysis and what it changed.",
                }
            ],
            "risks_to_address": [
                {
                    "requirement_id": identifier,
                    "risk": "May be probed without supporting evidence.",
                    "mitigation": "Prepare an honest answer and a learning plan.",
                }
                for identifier in gap_ids
            ],
        }

    def _questions(self, prompt: str) -> dict[str, Any]:
        gap_ids = set(self._gap_ids(prompt))
        questions = []
        for index in range(1, 9):
            requirement_id = "REQ-002" if index % 2 == 0 else "REQ-001"
            cited = (
                []
                if requirement_id in gap_ids
                else (["CL-001"] if requirement_id == "REQ-002" else ["EV-001"])
            )
            questions.append(question_payload(index, requirement_id, cited))
        return {"mock_questions": questions}


def _coverage_lines(prompt: str, coverage: str) -> list[str]:
    lines = []
    block = prompt.split("----- MATCHES -----")
    if len(block) < 2:
        return lines
    entries = block[1].split("}")
    for entry in entries:
        if f'"coverage": "{coverage}"' in entry and '"requirement_id"' in entry:
            lines.append(entry)
    return lines


GENERATE = {
    "next_action": "GENERATE_PREP_PACKAGE",
    "reason_summary": "Nothing has been generated yet.",
}
FINISH = {"next_action": "FINISH", "reason_summary": "The package is valid."}
ASK = {
    "next_action": "ASK_USER",
    "target_requirement_id": "REQ-002",
    "question": "What controlled experiments have you designed, and what changed?",
    "reason_summary": "The highest-importance requirement has no evidence.",
}


def run(
    decisions: list[dict[str, Any]],
    answers: list[str] | None = None,
    settings: Settings | None = None,
    tmp_path=None,
):
    provider = ScriptedProvider(decisions)
    supplied = list(answers or [])
    asked: list[tuple[str, str]] = []

    def ask_callback(requirement_id: str, question: str) -> str:
        asked.append((requirement_id, question))
        return supplied.pop(0)

    state, trace = run_agent(
        JOB_DESCRIPTION,
        EVIDENCE_YAML,
        "corpus",
        ask_callback,
        settings or Settings(),
        tmp_path,
        model=provider,
        extractor=scripted_extractor,
    )
    return state, trace, provider, asked


def test_enough_evidence_generates_then_finishes(tmp_path):
    # With the question budget at zero, the gap cannot be asked about, so the
    # loop generates once and finishes on the valid package.
    state, trace, provider, asked = run(
        [GENERATE, FINISH], settings=Settings(max_questions_per_run=0)
    )

    assert state["stop_reason"] == STOP_VALID_PACKAGE
    assert state["package_valid"] is True
    assert state["action_count"] == 2
    assert asked == []
    assert [entry["node"] for entry in trace if entry["node"] in ("generate", "finish")] == [
        "generate",
        "finish",
    ]


def test_gap_ask_resume_regenerate_finish(tmp_path):
    state, trace, provider, asked = run(
        [GENERATE, ASK, GENERATE, FINISH], answers=[ANSWER], tmp_path=tmp_path
    )

    # The interrupt carried the requirement and the question.
    assert asked == [("REQ-002", ASK["question"])]
    interrupt_entries = [
        entry for entry in trace if entry["node"] == "ask" and "interrupt" in entry
    ]
    assert interrupt_entries[0]["interrupt"][0]["requirement_id"] == "REQ-002"

    # The answer was minted as first-class clarification evidence.
    minted = state["clarification_evidence"]
    assert [item.id for item in minted] == ["CL-001"]
    assert minted[0].addresses_requirement_id == "REQ-002"
    assert minted[0].question == ASK["question"]
    assert minted[0].summary == ANSWER

    # Regeneration consumed it: the requirement is now covered by CL-001.
    verdict = next(v for v in state["matches"] if v.requirement_id == "REQ-002")
    assert verdict.coverage.value == "FULL"
    assert [match.evidence_id for match in verdict.matches] == ["CL-001"]

    assert state["package_valid"] is True
    assert state["stop_reason"] == STOP_VALID_PACKAGE
    assert state["action_count"] == 4

    # Artifacts include the loop's own record.
    assert (tmp_path / "agent_trace.json").is_file()
    assert (tmp_path / "prep_package.json").is_file()


def test_budget_exhaustion_terminates():
    state, trace, provider, asked = run(
        [GENERATE, GENERATE], settings=Settings(max_agent_actions=1, max_questions_per_run=0)
    )

    assert state["stop_reason"] == STOP_BUDGET_EXHAUSTED
    assert state.get("package_valid") is True  # the one generate ran
    assert state["action_count"] == 1
    assert trace[-1] == {"node": "stop", "stop_reason": STOP_BUDGET_EXHAUSTED}


def test_invalid_decision_retries_once_with_the_error_then_stops():
    # FINISH is proposed before anything is generated: not in the allowed set.
    state, trace, provider, asked = run([FINISH, FINISH])

    assert state["stop_reason"] == STOP_INVALID_DECISION
    assert state.get("package_generated", False) is False
    assert len(provider.decision_prompts) == 2
    assert "PRIOR PROPOSAL REJECTED BY CODE" in provider.decision_prompts[1]
    assert "not in the allowed set" in provider.decision_prompts[1]
    routes = [entry.get("route") for entry in trace if entry["node"] == "authorize"]
    assert routes == ["retry", "invalid"]

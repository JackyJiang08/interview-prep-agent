"""End-to-end trajectories through the evidence-gated loop, fully offline."""

from __future__ import annotations

import json
from typing import Any

from interview_prep_agent import Requirement, StructuredModel
from interview_prep_agent.agent import (
    CEILING_NOTE,
    STOP_VALID_PACKAGE,
    run_agent,
)
from interview_prep_agent.config import Settings
from interview_prep_agent.models import CoverageLevel

JOB_DESCRIPTION = """Requirements
- Strong SQL and Python for analysis on large datasets
- Designing controlled experiments for product decisions
- Presenting recommendations to senior leadership
- Operating production Kubernetes clusters
"""

EVIDENCE_YAML = """\
- id: EV-001
  summary: Owned SQL and Python analysis on large datasets
  skills: [sql, python, analysis]
"""

TEXTS = [
    ("Strong SQL and Python for analysis on large datasets", 3),
    ("Designing controlled experiments for product decisions", 5),
    ("Presenting recommendations to senior leadership", 4),
    ("Operating production Kubernetes clusters", 2),
]

# Answers whose vocabulary covers their requirement, so an admitted claim is
# rematched to FULL by the lexical matcher and cited by its CL- identifier.
ANSWERS = {
    "REQ-002": "I spent a year designing controlled experiments for product decisions.",
    "REQ-003": "Maybe I could present recommendations someday.",
    "REQ-004": "I operated production Kubernetes clusters for two years on call.",
}
CLAIMS = {
    "REQ-002": "Designing controlled experiments for product decisions for a year.",
    "REQ-004": "Operating production Kubernetes clusters on call for two years.",
}


def scripted_extractor(job_description: str) -> list[Requirement]:
    return [
        Requirement(
            id=f"REQ-{index:03d}",
            text=text,
            normalized=text.casefold(),
            source_quote=text,
            importance=importance,
        )
        for index, (text, importance) in enumerate(TEXTS, start=1)
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
    """Serve every model stage offline, keyed by the requested schema."""

    def __init__(self, round_payload: dict[str, Any] | None = None) -> None:
        self.round_payload = round_payload
        self.workflow_runs = 0
        self.assessments_requested: list[str] = []

    @property
    def name(self) -> str:
        return "scripted"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        properties = set(response_schema.get("properties", {}))
        if "round_type" in properties:
            return self.round_payload or {}
        if "is_valid" in properties:
            return self._assessment(prompt)
        if "top_priorities" in properties:
            self.workflow_runs += 1
            return self._strategy(prompt)
        if "mock_questions" in properties:
            return self._questions(prompt)
        raise AssertionError(f"unexpected schema: {sorted(properties)}")

    def _target(self, prompt: str) -> str:
        block = prompt.split("----- TARGET REQUIREMENT -----")[1]
        return block.split('"requirement_id": "')[1].split('"')[0]

    def _assessment(self, prompt: str) -> dict[str, Any]:
        target = self._target(prompt)
        self.assessments_requested.append(target)
        if target in CLAIMS:
            return {
                "target_requirement_id": target,
                "is_valid": True,
                "relevance_reason": "The answer addresses the requirement directly.",
                "specificity_reason": "It names concrete work and a result.",
                "accepted_claim": CLAIMS[target],
            }
        return {
            "target_requirement_id": target,
            "is_valid": False,
            "relevance_reason": "The answer states an aspiration, not experience.",
            "specificity_reason": "No concrete action or result is named.",
            "accepted_claim": None,
        }

    def _gap_ids(self, prompt: str) -> list[str]:
        ids = []
        block = prompt.split("----- MATCHES -----")
        if len(block) < 2:
            return ids
        for entry in block[1].split("}"):
            if '"coverage": "GAP"' in entry and '"requirement_id"' in entry:
                ids.append(entry.split('"requirement_id": "')[1].split('"')[0])
        return ids

    def _strategy(self, prompt: str) -> dict[str, Any]:
        gap_ids = self._gap_ids(prompt)
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
                    "requirement_id": identifier,
                    "risk": "May be probed without supporting evidence.",
                    "mitigation": "Prepare an honest answer and a learning plan.",
                }
                for identifier in gap_ids
            ],
        }

    def _questions(self, prompt: str) -> dict[str, Any]:
        gap_ids = set(self._gap_ids(prompt))
        cited_by_requirement = {
            "REQ-001": ["EV-001"],
            "REQ-002": ["CL-001"],
            "REQ-004": ["CL-002"],
        }
        questions = []
        identifiers = ["REQ-001", "REQ-002", "REQ-003", "REQ-004"] * 2
        for index, requirement_id in enumerate(identifiers, start=1):
            cited = (
                [] if requirement_id in gap_ids else cited_by_requirement.get(requirement_id, [])
            )
            questions.append(question_payload(index, requirement_id, cited))
        return {"mock_questions": questions}


def run(settings: Settings | None = None, tmp_path=None, round_text: str = ""):
    provider = ScriptedProvider()
    asked: list[tuple[str, str]] = []

    def ask_callback(requirement_id: str, question: str) -> str:
        asked.append((requirement_id, question))
        return ANSWERS[requirement_id]

    state, trace = run_agent(
        JOB_DESCRIPTION,
        EVIDENCE_YAML,
        "corpus",
        ask_callback,
        settings or Settings(),
        tmp_path,
        model=provider,
        extractor=scripted_extractor,
        round_text=round_text,
    )
    return state, trace, provider, asked


def test_three_answers_admitted_rejected_admitted(tmp_path):
    state, trace, provider, asked = run(tmp_path=tmp_path)

    # Queue order by importance: REQ-002 (5), REQ-003 (4), REQ-004 (2).
    assert [item[0] for item in asked] == ["REQ-002", "REQ-003", "REQ-004"]

    # The workflow graph ran exactly twice for the whole run.
    assert provider.workflow_runs == 2

    # Audit records show all three outcomes with reasons.
    records = state["clarification_records"]
    assert [record.accepted for record in records] == [True, False, True]
    assert "aspiration" in records[1].decision_reason
    assert records[0].accepted_claim == CLAIMS["REQ-002"]

    # Admitted claims minted CL- evidence whose summary is the claim.
    minted = state["clarification_evidence"]
    assert [item.id for item in minted] == ["CL-001", "CL-002"]
    assert minted[0].summary == CLAIMS["REQ-002"]
    assert minted[0].summary != ANSWERS["REQ-002"]

    # The final rematch cites the admitted claims by their CL- identifiers.
    verdicts = {v.requirement_id: v for v in state["matches"]}
    assert verdicts["REQ-002"].coverage is CoverageLevel.FULL
    assert [m.evidence_id for m in verdicts["REQ-002"].matches] == ["CL-001"]
    assert verdicts["REQ-004"].coverage is CoverageLevel.FULL
    assert [m.evidence_id for m in verdicts["REQ-004"].matches] == ["CL-002"]

    # The rejected requirement stays a gap and surfaces as a risk.
    assert verdicts["REQ-003"].coverage is CoverageLevel.GAP
    package = state["prep_package"]
    assert "REQ-003" in [risk.requirement_id for risk in package.strategy.risks_to_address]

    assert state["stop_reason"] == STOP_VALID_PACKAGE
    assert (tmp_path / "clarification_records.json").is_file()
    payload = json.loads((tmp_path / "clarification_records.json").read_text())
    assert [entry["accepted"] for entry in payload] == [True, False, True]
    trace_payload = json.loads((tmp_path / "agent_trace.json").read_text())
    assert trace_payload[0]["node"] == "parse_round"
    assert trace_payload[0]["round"] is None


def test_question_ceiling_asks_only_the_top_gap():
    state, trace, provider, asked = run(settings=Settings(max_questions_per_run=1))

    assert [item[0] for item in asked] == ["REQ-002"]
    assert provider.workflow_runs == 2
    assert state["stop_reason"] == STOP_VALID_PACKAGE
    assert state["final_note"] == CEILING_NOTE
    notes = [entry.get("note") for entry in trace if entry["node"] == "generate_final"]
    assert notes == [CEILING_NOTE]

    # The unasked gaps are still gaps in the final package.
    verdicts = {v.requirement_id: v for v in state["matches"]}
    assert verdicts["REQ-003"].coverage is CoverageLevel.GAP
    assert verdicts["REQ-004"].coverage is CoverageLevel.GAP


def test_round_text_is_parsed_once_and_recorded():
    provider = ScriptedProvider(
        round_payload={
            "round_type": "technical screen",
            "interviewer_roles": ["engineering manager"],
            "focus": ["experiment design"],
        }
    )
    state, trace = run_agent(
        JOB_DESCRIPTION,
        EVIDENCE_YAML,
        "corpus",
        lambda rid, q: ANSWERS[rid],
        Settings(max_questions_per_run=0),
        None,
        model=provider,
        extractor=scripted_extractor,
        round_text="Second round: technical screen with the engineering manager.",
    )

    assert state["round_context"].round_type == "technical screen"
    parse_entries = [entry for entry in trace if entry["node"] == "parse_round"]
    assert parse_entries[0]["round"]["round_type"] == "technical screen"
    assert state["stop_reason"] == STOP_VALID_PACKAGE


def test_absent_round_proceeds_with_none():
    state, trace, provider, asked = run(settings=Settings(max_questions_per_run=0))

    assert state["round_context"] is None
    assert state["stop_reason"] == STOP_VALID_PACKAGE
    assert asked == []
    # Both generations still ran; no questions were asked.
    assert provider.workflow_runs == 2

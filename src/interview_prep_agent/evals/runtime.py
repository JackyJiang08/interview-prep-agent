"""Providers for the two suites, injected through the existing seam.

Nothing here monkeypatches anything. The offline suite hands the compiled
graph a fixture provider through the same ``model=`` injection point the
trajectory tests use; the live suite wraps the real provider so genuine calls
can be counted. The production code path is identical either way.
"""

from __future__ import annotations

import json
from typing import Any

from ..providers import StructuredModel


def _json_between(text: str, start: str, end: str | None = None) -> Any:
    fragment = text.split(start, 1)[1]
    if end is not None:
        fragment = fragment.split(end, 1)[0]
    return json.loads(fragment.strip())


def _matches_rows(prompt: str) -> list[dict[str, Any]]:
    for terminator in ("----- FOCUS AREAS -----", "----- STRATEGY -----"):
        if terminator in prompt:
            return _json_between(prompt, "----- MATCHES -----", terminator)
    raise AssertionError("the preparation prompt carried no matches block")


def _round_label(prompt: str) -> str:
    if "----- INTERVIEW ROUND -----" not in prompt:
        return "general preparation"
    payload = _json_between(prompt, "----- INTERVIEW ROUND -----")
    return payload.get("round_type") or "general preparation"


class FixtureProvider(StructuredModel):
    """Deterministic stand-in for every model stage of one scenario run.

    Dispatch is on the requested response schema, then on prompt content —
    the same contract a real provider sees, so drift in either schema or
    prompt structure fails loudly here instead of silently in a fixture.
    """

    def __init__(self, assessments_by_requirement: dict[str, dict[str, Any]]) -> None:
        self.assessments_by_requirement = assessments_by_requirement
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "behavior-fixture"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        properties = set(response_schema.get("properties", {}))
        self.calls.append(",".join(sorted(properties)))
        if "round_type" in properties:
            return self._round(prompt)
        if "top_priorities" in properties:
            return self._strategy(prompt)
        if "mock_questions" in properties:
            return self._questions(prompt)
        if "is_valid" in properties:
            return self._assessment(prompt)
        raise AssertionError(f"unexpected response schema: {sorted(properties)}")

    def _round(self, prompt: str) -> dict[str, Any]:
        description = prompt.split("----- ROUND DESCRIPTION -----", 1)[1].strip()
        lowered = description.casefold()
        if "panel" in lowered:
            return {
                "round_type": "cross-functional panel",
                "format": None,
                "interviewer_roles": ["product manager", "engineering lead"],
                "focus": ["stakeholder alignment", "concise recommendations"],
                "notes": None,
            }
        if "case" in lowered:
            return {
                "round_type": "analytics case",
                "format": "60-minute live case",
                "interviewer_roles": ["hiring manager"],
                "focus": ["hypothesis testing", "trade-offs"],
                "notes": None,
            }
        return {
            "round_type": "hiring-manager discussion",
            "format": None,
            "interviewer_roles": ["hiring manager"],
            "focus": ["technical depth", "honest gaps"],
            "notes": None,
        }

    def _strategy(self, prompt: str) -> dict[str, Any]:
        rows = _matches_rows(prompt)
        label = _round_label(prompt)
        supported = [row for row in rows if row["coverage"] != "GAP"]
        gaps = [row for row in rows if row["coverage"] == "GAP"]
        return {
            "top_priorities": [
                {
                    "requirement_id": row["requirement_id"],
                    "evidence_ids": row["evidence_ids"],
                    "preparation_theme": (f"Prepare {row['requirement_id']} for the {label}."),
                    "rationale": "Use the validated coverage and evidence links.",
                }
                for row in supported
            ],
            "positioning_statement": (
                f"Lead with grounded evidence tailored to the {label}, "
                "treating remaining gaps honestly."
            ),
            "stories_to_prepare": [
                {
                    "requirement_id": row["requirement_id"],
                    "evidence_ids": row["evidence_ids"],
                    "story_to_prepare": (f"An evidence-linked account of {row['requirement_id']}."),
                }
                for row in supported
            ],
            "risks_to_address": [
                {
                    "requirement_id": row["requirement_id"],
                    "risk": f"{row['requirement_id']} has no supporting evidence.",
                    "mitigation": "Acknowledge the gap and bring a learning plan.",
                }
                for row in gaps
            ],
        }

    def _questions(self, prompt: str) -> dict[str, Any]:
        rows = _matches_rows(prompt)
        label = _round_label(prompt)
        questions = []
        index = 0
        while len(questions) < 8:
            row = rows[index % len(rows)]
            index += 1
            cited = [] if row["coverage"] == "GAP" else row["evidence_ids"]
            questions.append(
                {
                    "question": (
                        f"In the {label}, how would you speak to "
                        f"{row['requirement_id']} (variant {index})?"
                    ),
                    "requirement_id": row["requirement_id"],
                    "capability_tested": "grounded evidence",
                    "evidence_ids": cited,
                    "follow_up_probe": "What concrete evidence supports that?",
                    "answer_outline": [
                        "State the relevant evidence or the honest gap.",
                        "Explain the action and the result.",
                    ],
                }
            )
        return {"mock_questions": questions}

    def _assessment(self, prompt: str) -> dict[str, Any]:
        target = _json_between(prompt, "----- TARGET REQUIREMENT -----", "----- QUESTION -----")
        requirement_id = target["requirement_id"]
        try:
            return self.assessments_by_requirement[requirement_id]
        except KeyError as error:
            raise AssertionError(
                f"the scenario scripted no assessment for {requirement_id}"
            ) from error


class CountingProvider(StructuredModel):
    """Delegate to a real provider while recording that real calls happened."""

    def __init__(self, inner: StructuredModel) -> None:
        self.inner = inner
        self.call_count = 0

    @property
    def name(self) -> str:
        return self.inner.name

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        self.call_count += 1
        return self.inner.generate_json(prompt, response_schema)

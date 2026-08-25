"""Stage 4, model-backed - turn the strategy into practice questions.

The same discipline as every model stage: one structured-output call, schema
validation here, deterministic reference checking in the gates. The question
floor is deliberately not enforced in the response schema — a shortfall is a
package-gate finding that routes the run to its error report, not a parse
failure.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..models import (
    InterviewRound,
    InterviewStrategy,
    MockQuestion,
    MockQuestionList,
    Requirement,
    RequirementMatch,
    ResearchFinding,
)
from ..providers import ProviderError, StructuredModel
from .strategy import _research_section, _round_section

MIN_QUESTIONS = 8
MAX_REQUESTED_QUESTIONS = 12

QUESTION_INSTRUCTIONS = f"""\
You write realistic practice questions for an upcoming interview, grounded in
the supplied strategy.

Rules:

- Return {MIN_QUESTIONS} to {MAX_REQUESTED_QUESTIONS} questions covering the
  top priorities and the risks.
- Every question carries a requirement_id that appears in the supplied
  requirements.
- A question may cite only evidence_ids already matched to its requirement.
  A question probing a GAP requirement cites no evidence and its answer
  outline coaches an honest response, never invented experience.
- Give each question a follow-up probe an interviewer would plausibly ask,
  and at least two concise answer-outline points.
- When an interview round section is supplied, weight the questions toward
  that round's type and focus. Round context changes what to emphasize,
  never what the candidate can claim.
- When a role research section is supplied, use it to make questions
  realistic - reported themes, phrasing, expectations - and you may cite a
  finding inline by its SRC- identifier. Findings are role intelligence, not
  candidate evidence: never cite one as support for a match.

Return nothing except data conforming to the supplied schema.
"""


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_question_prompt(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    strategy: InterviewStrategy,
    round_context: InterviewRound | None = None,
    research: Sequence[ResearchFinding] = (),
) -> str:
    """Place the validated state after the instructions, with boundaries."""
    requirement_rows = [{"requirement_id": r.id, "requirement": r.text} for r in requirements]
    match_rows = [
        {
            "requirement_id": v.requirement_id,
            "coverage": v.coverage.value if v.coverage else v.status.value,
            "evidence_ids": [m.evidence_id for m in v.matches],
        }
        for v in verdicts
    ]
    return (
        f"{QUESTION_INSTRUCTIONS}\n"
        "----- REQUIREMENTS -----\n"
        f"{_dump(requirement_rows)}\n"
        "----- MATCHES -----\n"
        f"{_dump(match_rows)}\n"
        "----- STRATEGY -----\n"
        f"{_dump(strategy.model_dump(mode='json'))}\n"
        f"{_round_section(round_context)}"
        f"{_research_section(research)}"
    )


def response_schema() -> dict[str, Any]:
    """Return the JSON Schema requested from the provider."""
    return MockQuestionList.model_json_schema()


def parse_questions(payload: Any) -> list[MockQuestion]:
    """Validate a provider response into questions.

    Raises:
        ProviderError: If the payload does not satisfy the schema.
    """
    try:
        return MockQuestionList.model_validate(payload, from_attributes=True).mock_questions
    except Exception as error:  # noqa: BLE001 - pydantic raises several types
        raise ProviderError(
            f"model response did not match the requested schema: {error}"
        ) from error


def generate_questions_with_model(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    strategy: InterviewStrategy,
    model: StructuredModel,
    round_context: InterviewRound | None = None,
    research: Sequence[ResearchFinding] = (),
) -> list[MockQuestion]:
    """Generate practice questions using a provider.

    Raises:
        ProviderError: If the call fails or the response cannot be used.
    """
    payload = model.generate_json(
        build_question_prompt(requirements, verdicts, strategy, round_context, research),
        response_schema(),
    )
    return parse_questions(payload)

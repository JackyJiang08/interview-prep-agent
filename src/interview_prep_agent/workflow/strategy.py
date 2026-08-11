"""Stage 3, model-backed - turn focus areas into an interview strategy.

One structured-output call through the provider seam. The model composes; it
does not certify. Its output is validated against the requested schema here
and held to the strategy gate before anything downstream reads it, and every
identifier it uses must already exist in the state it was shown.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..models import (
    FocusArea,
    InterviewStrategy,
    Requirement,
    RequirementMatch,
)
from ..providers import ProviderError, StructuredModel

STRATEGY_INSTRUCTIONS = """\
You write a concise interview-preparation strategy from validated workflow
state.

Rules:

- Prioritise high-priority PARTIAL and GAP focus areas; use FULL matches as
  the stories that prove strengths.
- Every top_priorities item, story and risk carries a requirement_id that
  appears in the supplied requirements.
- An item may cite only evidence_ids already matched to its requirement. An
  item for a GAP requirement cites no evidence at all — coach an honest
  answer instead of inventing experience.
- Cover every GAP focus area in risks_to_address, each with a concrete
  mitigation the candidate can actually do before the interview.
- The positioning statement is grounded in the supplied matches, not in
  anything imagined about the candidate.

Return nothing except data conforming to the supplied schema.
"""


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_strategy_prompt(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    focus_areas: Sequence[FocusArea],
) -> str:
    """Place the validated state after the instructions, with boundaries."""
    requirement_rows = [
        {"requirement_id": r.id, "requirement": r.text, "importance": r.importance}
        for r in requirements
    ]
    match_rows = [
        {
            "requirement_id": v.requirement_id,
            "coverage": v.coverage.value if v.coverage else v.status.value,
            "evidence_ids": [m.evidence_id for m in v.matches],
            "explanation": v.explanation,
        }
        for v in verdicts
    ]
    focus_rows = [area.model_dump(mode="json") for area in focus_areas]
    return (
        f"{STRATEGY_INSTRUCTIONS}\n"
        "----- REQUIREMENTS -----\n"
        f"{_dump(requirement_rows)}\n"
        "----- MATCHES -----\n"
        f"{_dump(match_rows)}\n"
        "----- FOCUS AREAS -----\n"
        f"{_dump(focus_rows)}\n"
    )


def response_schema() -> dict[str, Any]:
    """Return the JSON Schema requested from the provider."""
    return InterviewStrategy.model_json_schema()


def parse_strategy(payload: Any) -> InterviewStrategy:
    """Validate a provider response into a strategy.

    Raises:
        ProviderError: If the payload does not satisfy the schema.
    """
    try:
        return InterviewStrategy.model_validate(payload, from_attributes=True)
    except Exception as error:  # noqa: BLE001 - pydantic raises several types
        raise ProviderError(
            f"model response did not match the requested schema: {error}"
        ) from error


def build_strategy_with_model(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    focus_areas: Sequence[FocusArea],
    model: StructuredModel,
) -> InterviewStrategy:
    """Compose the strategy using a provider.

    Deterministic reference checking belongs to the gates; this function
    guarantees only that the response parses into the schema it requested.

    Raises:
        ProviderError: If the call fails or the response cannot be used.
    """
    payload = model.generate_json(
        build_strategy_prompt(requirements, verdicts, focus_areas), response_schema()
    )
    return parse_strategy(payload)

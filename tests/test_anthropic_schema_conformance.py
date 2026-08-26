"""Every schema the app sends through the Anthropic provider conforms.

The hole this closes: the provider sent Pydantic-derived schemas verbatim,
and the API rejects value bounds its constrained decoding does not support.
A list bounded to two through five items was enough for a 400 in a real
run. This walks every response model the app requests through the seam,
sends each through the provider with the vendor client mocked, and checks
both that the provider used the transformed schema and that the transformed
schema carries none of the rejected keywords. The failing case is here as
an explicit model, so the test bites on exactly what shipped.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from anthropic import transform_schema
from pydantic import BaseModel, Field

from interview_prep_agent.models import (
    ClarificationAssessment,
    CraftedQuestion,
    InterviewRound,
    InterviewStrategy,
    MatchAssessmentList,
    MockQuestionList,
    RequirementExtraction,
)
from interview_prep_agent.providers.anthropic import AnthropicModel

# The complete set of response models the app asks a provider for: extraction,
# matching, assessment, round parsing, strategy, questions.
REQUESTED_MODELS = [
    RequirementExtraction,
    MatchAssessmentList,
    ClarificationAssessment,
    CraftedQuestion,
    InterviewRound,
    InterviewStrategy,
    MockQuestionList,
]

REJECTED_KEYWORDS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
}


class BoundedList(BaseModel):
    """The case that failed live: an array bounded to two through five."""

    items: list[str] = Field(min_length=2, max_length=5)


def _offences(node: Any, path: str = "$") -> list[str]:
    """Every rejected keyword in a schema, with where it sits."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}"
            if key in REJECTED_KEYWORDS:
                found.append(here)
            elif key in ("minItems", "maxItems") and value not in (0, 1):
                found.append(f"{here}={value}")
            found.extend(_offences(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_offences(value, f"{path}[{index}]"))
    return found


def _send_through_provider(monkeypatch, schema: dict[str, Any]) -> dict[str, Any]:
    """Run one request through the provider and return the schema it sent."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key-TESTSECRET-1414")
    model = AnthropicModel()
    sent: list[dict[str, Any]] = []

    def create(**kwargs):
        sent.append(kwargs["output_config"]["format"]["schema"])
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="{}")], stop_reason="end_turn"
        )

    model._client = SimpleNamespace(messages=SimpleNamespace(create=create))  # noqa: SLF001
    model.generate_json("a prompt", schema)
    return sent[0]


@pytest.mark.parametrize("model_class", REQUESTED_MODELS, ids=lambda cls: cls.__name__)
def test_every_requested_schema_conforms_after_the_provider_transform(monkeypatch, model_class):
    derived = model_class.model_json_schema()
    sent = _send_through_provider(monkeypatch, derived)

    # (a) The provider path uses the transformed schema, not the derived one.
    assert sent == transform_schema(derived)
    # (b) Nothing the API rejects survives the transform.
    assert _offences(sent) == []


def test_the_case_that_failed_live_is_stripped_and_would_have_been_caught(monkeypatch):
    derived = BoundedList.model_json_schema()
    # The derived schema carries the bounds — this is what shipped.
    assert set(_offences(derived)) == {
        "$.properties.items.minItems=2",
        "$.properties.items.maxItems=5",
    }

    sent = _send_through_provider(monkeypatch, derived)
    assert _offences(sent) == []
    assert "minItems" not in sent["properties"]["items"]
    assert "maxItems" not in sent["properties"]["items"]
    # The bound is not lost: it rides in the description for the model to
    # read, and the caller's Pydantic validation enforces it after parsing.
    assert "minItems: 2" in sent["properties"]["items"]["description"]
    assert "maxItems: 5" in sent["properties"]["items"]["description"]
    with pytest.raises(ValueError):
        BoundedList.model_validate({"items": ["only one"]})


def test_the_offence_walker_sees_every_rejected_keyword():
    # The walker itself must not have a blind spot, or the suite above is
    # a false comfort.
    schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 1, "maximum": 9, "exclusiveMaximum": 10},
            "s": {"type": "string", "minLength": 1, "maxLength": 5, "pattern": "^x"},
            "a": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
            "ok": {"type": "array", "items": {"type": "string"}, "minItems": 0, "maxItems": 1},
        },
        "$defs": {"Inner": {"type": "number", "exclusiveMinimum": 0}},
    }
    found = _offences(schema)
    assert len(found) == 8
    assert "$.properties.a.maxItems=3" in found
    assert not any(item.startswith("$.properties.ok") for item in found)
    assert "$.$defs.Inner.exclusiveMinimum" in found


def test_the_app_schemas_carry_bounds_the_transform_must_strip():
    # Proof that the hole was real for the app itself, not only for the
    # hand-written case: at least one requested schema carries a bound.
    offending = {
        cls.__name__: _offences(cls.model_json_schema())
        for cls in REQUESTED_MODELS
        if _offences(cls.model_json_schema())
    }
    assert offending, "no requested schema carries a bound; the conformance test is vacuous"

"""Tests for model-backed extraction, with the provider seam mocked.

Nothing here reaches the network. The seam exists precisely so that the node's
behaviour — what it asks for, and what it refuses to accept — can be tested
without credentials, which is what keeps CI offline.
"""

from __future__ import annotations

from typing import Any

import pytest

from interview_prep_agent import ProviderError, StructuredModel
from interview_prep_agent.workflow.extract_model import (
    extract_requirements_with_model,
    parse_extraction,
    response_schema,
)


class RecordingModel(StructuredModel):
    """A provider that returns a canned payload and records its inputs."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def name(self) -> str:
        return "recording"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        self.calls.append((prompt, response_schema))
        return self.payload


def one_requirement(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": "REQ-001",
        "text": "Strong SQL and Python for analysis on large datasets",
        "normalized": "strong sql and python for analysis on large datasets",
        "source_quote": "Strong SQL and Python for analysis on large datasets",
        "category": "technical",
        "importance": 5,
        "requirement_type": "must_have",
    }
    payload.update(overrides)
    return payload


def test_a_response_schema_is_requested():
    model = RecordingModel({"requirements": [one_requirement()]})

    extract_requirements_with_model("Some posting", model)

    prompt, schema = model.calls[0]
    assert "Some posting" in prompt
    assert schema == response_schema()
    assert "requirements" in schema["properties"]


def test_the_parsed_response_is_validated_into_models():
    model = RecordingModel({"requirements": [one_requirement()]})

    requirements = extract_requirements_with_model("Some posting", model)

    assert len(requirements) == 1
    assert requirements[0].id == "REQ-001"
    assert requirements[0].category.value == "technical"
    assert requirements[0].importance == 5


def test_a_response_failing_the_schema_raises():
    model = RecordingModel({"requirements": [one_requirement(id="requirement-1")]})

    with pytest.raises(ProviderError, match="did not match the requested schema"):
        extract_requirements_with_model("Some posting", model)


def test_an_unexpected_field_raises_rather_than_passing_through():
    model = RecordingModel({"requirements": [one_requirement(confidence=0.9)]})

    with pytest.raises(ProviderError, match="did not match the requested schema"):
        extract_requirements_with_model("Some posting", model)


def test_a_response_omitting_a_model_only_field_raises():
    payload = one_requirement()
    del payload["category"]
    model = RecordingModel({"requirements": [payload]})

    with pytest.raises(ProviderError, match="omitted category"):
        extract_requirements_with_model("Some posting", model)


def test_a_response_omitting_the_source_quote_raises():
    payload = one_requirement()
    del payload["source_quote"]

    with pytest.raises(ProviderError, match="omitted source_quote"):
        parse_extraction({"requirements": [payload]})


def test_a_wholly_malformed_payload_raises():
    with pytest.raises(ProviderError, match="did not match the requested schema"):
        parse_extraction("not a mapping at all")


def test_importance_outside_the_scale_raises():
    with pytest.raises(ProviderError, match="did not match the requested schema"):
        parse_extraction({"requirements": [one_requirement(importance=9)]})

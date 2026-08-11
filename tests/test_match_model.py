"""Tests for the coverage mapping of both matcher paths.

The lexical mapping is exercised directly; the model path runs against the
recording provider from the extraction tests — nothing here reaches the
network.
"""

from __future__ import annotations

from typing import Any

import pytest

from interview_prep_agent import (
    CoverageLevel,
    EvidenceItem,
    ProviderError,
    Requirement,
    Status,
    StructuredModel,
    match_requirements,
)
from interview_prep_agent.workflow.match_model import (
    match_evidence_with_model,
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


def requirement(index: int, text: str, importance: int | None = None) -> Requirement:
    return Requirement(
        id=f"REQ-{index:03d}",
        text=text,
        normalized=text.casefold(),
        source_quote=text,
        importance=importance,
    )


EVIDENCE = [
    EvidenceItem(id="EV-001", summary="Wrote SQL and Python analysis on large datasets"),
    EvidenceItem(id="EV-002", summary="Ran weekly reviews with product partners"),
]


def assessment(index: int, coverage: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "requirement_id": f"REQ-{index:03d}",
        "evidence_ids": evidence_ids,
        "coverage": coverage,
        "explanation": "Judged from the supplied claims only.",
        "confidence": 0.8,
    }


# --- lexical mapping ---------------------------------------------------------


def test_lexical_score_at_threshold_is_full():
    requirements = [requirement(1, "SQL and Python analysis on large datasets")]
    verdicts = match_requirements(requirements, EVIDENCE, threshold=1.0, max_matches=3)
    assert verdicts[0].coverage is CoverageLevel.FULL
    assert verdicts[0].confidence == 1.0
    assert verdicts[0].status is Status.PROOF


def test_lexical_score_below_threshold_is_gap_with_zero_confidence():
    requirements = [requirement(1, "Kubernetes service mesh operations")]
    verdicts = match_requirements(requirements, EVIDENCE, threshold=0.3, max_matches=3)
    assert verdicts[0].coverage is CoverageLevel.GAP
    assert verdicts[0].confidence == 0.0
    assert verdicts[0].matches == []


def test_lexical_never_emits_partial():
    requirements = [
        requirement(index, text)
        for index, text in enumerate(
            [
                "SQL and Python analysis on large datasets",
                "Weekly reviews with product partners",
                "Kubernetes service mesh operations",
                "SQL analysis plus Kubernetes operations",
            ],
            start=1,
        )
    ]
    for threshold in (0.0, 0.1, 0.3, 0.5, 0.9, 1.0):
        for verdict in match_requirements(requirements, EVIDENCE, threshold, 3):
            assert verdict.coverage is not CoverageLevel.PARTIAL


# --- model path --------------------------------------------------------------


def test_the_assessment_schema_is_requested():
    model = RecordingModel(
        {
            "assessments": [
                assessment(1, "FULL", ["EV-001"]),
            ]
        }
    )
    match_evidence_with_model([requirement(1, "SQL analysis")], EVIDENCE, model)

    prompt, schema = model.calls[0]
    assert schema == response_schema()
    assert "assessments" in schema["properties"]
    assert "REQ-001" in prompt
    assert "EV-001" in prompt


def test_gap_is_preserved_not_upgraded():
    model = RecordingModel(
        {
            "assessments": [
                assessment(1, "GAP", []),
            ]
        }
    )
    verdicts = match_evidence_with_model([requirement(1, "Kubernetes operations")], EVIDENCE, model)
    assert verdicts[0].coverage is CoverageLevel.GAP
    assert verdicts[0].status is Status.GAP
    assert verdicts[0].matches == []


def test_partial_maps_to_proof_with_citations():
    model = RecordingModel(
        {
            "assessments": [
                assessment(1, "PARTIAL", ["EV-001"]),
            ]
        }
    )
    verdicts = match_evidence_with_model([requirement(1, "SQL analysis")], EVIDENCE, model)
    assert verdicts[0].coverage is CoverageLevel.PARTIAL
    assert verdicts[0].status is Status.PROOF
    assert [match.evidence_id for match in verdicts[0].matches] == ["EV-001"]


def test_a_malformed_response_raises():
    model = RecordingModel({"assessments": [{"requirement_id": "REQ-001"}]})
    with pytest.raises(ProviderError, match="did not match the requested schema"):
        match_evidence_with_model([requirement(1, "SQL analysis")], EVIDENCE, model)


def test_an_unknown_coverage_value_raises():
    model = RecordingModel({"assessments": [assessment(1, "MOSTLY", ["EV-001"])]})
    with pytest.raises(ProviderError, match="did not match the requested schema"):
        match_evidence_with_model([requirement(1, "SQL analysis")], EVIDENCE, model)


def test_confidence_outside_the_unit_range_raises():
    payload = assessment(1, "FULL", ["EV-001"])
    payload["confidence"] = 1.4
    model = RecordingModel({"assessments": [payload]})
    with pytest.raises(ProviderError, match="did not match the requested schema"):
        match_evidence_with_model([requirement(1, "SQL analysis")], EVIDENCE, model)

"""A live session runs the model-backed stages end to end; a demo keeps lexical.

The defect this pins: the session driver never passed an extractor or a
matcher to the agent, so every session ran the lexical stages regardless of
the key it carried. The test runs a live session with the provider mocked
and reads the stage artifacts the session wrote.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interview_prep_agent.config import Settings
from interview_prep_agent.providers import StructuredModel
from interview_prep_agent.server.app import create_app
from interview_prep_agent.workflow.match import METHOD_NAME as LEXICAL_METHOD
from interview_prep_agent.workflow.match_model import METHOD_NAME as MODEL_METHOD

POSTING = """Job description
Data Analyst
Requirements:
- Strong SQL and Python for analysis on large datasets
- Designing controlled experiments for product decisions
Salary range $90,000 to $120,000 per year
"""

EVIDENCE = """- id: EV-001
  summary: Owned SQL and Python analysis on large datasets
  skills: [sql, python, analysis]
"""

REAL = [
    "Strong SQL and Python for analysis on large datasets",
    "Designing controlled experiments for product decisions",
]


class ScriptedLiveProvider(StructuredModel):
    """Serves every model stage offline, including extraction and matching.

    Extraction returns the two real requirements plus the heading and the
    salary line, exactly as a model did in the real run, so the guard has
    something to refuse. After the guard the real ones are REQ-001 (covered
    by EV-001) and REQ-002 (a gap).
    """

    def __init__(self) -> None:
        self.schemas_requested: list[str] = []

    @property
    def name(self) -> str:
        return "scripted-live"

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        properties = set(response_schema.get("properties", {}))
        title = response_schema.get("title", "")
        self.schemas_requested.append(title)
        if "requirements" in properties:
            texts = ["Job description", *REAL, "Salary range $90,000 to $120,000 per year"]
            return {
                "requirements": [
                    {
                        "id": f"REQ-{n:03d}",
                        "text": text,
                        "normalized": text.casefold(),
                        "source_quote": text,
                        "category": "analytics",
                        "importance": 4,
                        "requirement_type": "must_have",
                    }
                    for n, text in enumerate(texts, start=1)
                ]
            }
        if "assessments" in properties:
            ids = _ids(prompt)
            return {
                "assessments": [
                    {
                        "requirement_id": rid,
                        "evidence_ids": ["EV-001"] if rid == "REQ-001" else [],
                        "coverage": "FULL" if rid == "REQ-001" else "GAP",
                        "explanation": "Judged by the scripted model.",
                        "confidence": 0.9,
                    }
                    for rid in ids
                ]
            }
        if "round_type" in properties:
            return {}
        if "is_valid" in properties:
            return {
                "target_requirement_id": _target(prompt),
                "is_valid": False,
                "relevance_reason": "Scripted: not admitted.",
                "specificity_reason": "Scripted: not admitted.",
                "accepted_claim": None,
            }
        if "top_priorities" in properties:
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
            return {
                "mock_questions": [
                    {
                        "question": f"Practice question number {n}?",
                        "requirement_id": rid,
                        "capability_tested": "analysis",
                        "evidence_ids": ["EV-001"] if rid == "REQ-001" else [],
                        "follow_up_probe": "What changed as a result?",
                        "answer_outline": ["State the context.", "State the outcome."],
                    }
                    for n, rid in enumerate(["REQ-001", "REQ-002"] * 4, start=1)
                ]
            }
        raise AssertionError(f"unexpected schema: {sorted(properties)}")


def _ids(prompt: str) -> list[str]:
    return sorted({token for token in _tokens(prompt) if token.startswith("REQ-")})


def _tokens(prompt: str) -> list[str]:
    import re

    return re.findall(r"REQ-\d{3}", prompt)


def _target(prompt: str) -> str:
    block = prompt.split("----- TARGET REQUIREMENT -----")[1]
    return block.split('"requirement_id": "')[1].split('"')[0]


@pytest.fixture
def scripted(monkeypatch):
    provider = ScriptedLiveProvider()
    monkeypatch.setattr("interview_prep_agent.providers.build_model", lambda *a, **k: provider)
    return provider


def _run_live(client: TestClient, **overrides) -> tuple[dict, dict]:
    response = client.post(
        "/api/sessions",
        json={
            "mode": "live",
            "jd_text": POSTING,
            "evidence_text": EVIDENCE,
            "gemini_api_key": "gm-key-TESTSECRET-1111",
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]
    view = client.get(f"/api/sessions/{session_id}").json()
    seen: dict[str, list] = {"node_update": [], "interrupt": [], "error": []}
    with client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
        while True:
            message = ws.receive_json()
            if message["type"] == "done":
                break
            seen.setdefault(message["type"], []).append(message)
            if message["type"] == "interrupt":
                ws.send_json({"type": "answer", "text": "An answer that is long enough to assess."})
    artifacts = client.get(f"/api/sessions/{session_id}/artifacts").json()["files"]
    return view, {"seen": seen, "artifacts": artifacts}


def test_a_live_session_defaults_to_model_backed_stages_end_to_end(scripted):
    with TestClient(create_app(Settings())) as client:
        view, run = _run_live(client)
    assert (view["extractor"], view["matcher"]) == ("llm", "llm")
    assert run["seen"]["error"] == []

    requirements = run["artifacts"]["requirements.json"]
    # Model-backed extraction populates the fields the lexical path cannot.
    assert all(item.get("category") and item.get("importance") for item in requirements)
    assert [item["text"] for item in requirements] == REAL
    # Model-backed matching signs its verdicts with its own method.
    assert {item["method"] for item in run["artifacts"]["matches.json"]} == {MODEL_METHOD}
    # The guard's drops are in the artifacts and in the trace, never hidden.
    dropped = run["artifacts"]["dropped_requirements.json"]
    assert {item["text"] for item in dropped} == {
        "Job description",
        "Salary range $90,000 to $120,000 per year",
    }
    initial = next(
        item for item in run["seen"]["node_update"] if item["node"] == "generate_initial"
    )
    assert len(initial["delta"]["dropped"]) == 2
    # No question was asked about a heading or a salary line.
    asked = {item["requirement_id"] for item in run["seen"]["interrupt"]}
    assert asked == {"REQ-002"}


def test_the_lexical_override_is_honored_for_a_live_session(scripted):
    with TestClient(create_app(Settings())) as client:
        view, run = _run_live(client, extractor="lexical", matcher="lexical")
    assert (view["extractor"], view["matcher"]) == ("lexical", "lexical")
    assert {item["method"] for item in run["artifacts"]["matches.json"]} == {LEXICAL_METHOD}
    assert all("category" not in item for item in run["artifacts"]["requirements.json"])


def test_a_demo_session_keeps_the_lexical_stages():
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/sessions", json={"mode": "demo", "demo_id": "mixed-clarifications"}
        )
        view = client.get(f"/api/sessions/{response.json()['session_id']}").json()
    assert (view["extractor"], view["matcher"]) == ("lexical", "lexical")


def test_a_trace_artifact_is_written_for_every_session(scripted):
    with TestClient(create_app(Settings())) as client:
        _view, run = _run_live(client)
    trace = run["artifacts"]["agent_trace.json"]
    assert isinstance(json.loads(json.dumps(trace)), list)
    assert any(entry.get("dropped") for entry in trace if entry["node"] == "generate_initial")

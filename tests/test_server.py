"""Session-layer tests over the ASGI test client, fully offline."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from interview_prep_agent.config import Settings
from interview_prep_agent.server.app import create_app

MIXED_DEMO = "mixed-clarifications"
COMPLETE_DEMO = "complete-profile-no-round"


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def _create_demo(client: TestClient, demo_id: str) -> str:
    response = client.post("/api/sessions", json={"mode": "demo", "demo_id": demo_id})
    assert response.status_code == 201
    return response.json()["session_id"]


def _drain(ws, answers: dict[str, str]) -> dict[str, list]:
    """Consume one session's stream, answering interrupts from a script."""
    seen: dict[str, list] = {"node_update": [], "interrupt": [], "package": [], "error": []}
    while True:
        message = ws.receive_json()
        if message["type"] == "done":
            seen["done"] = message
            return seen
        seen[message["type"]].append(message)
        if message["type"] == "interrupt":
            ws.send_json({"type": "answer", "text": answers[message["requirement_id"]]})


def _demo_answers(client: TestClient, demo_id: str) -> dict[str, str]:
    demos = {item["demo_id"]: item for item in client.get("/api/demos").json()["demos"]}
    return demos[demo_id]["suggested_answers"]


# --- lifecycle ----------------------------------------------------------------


def test_demo_session_end_to_end(client):
    answers = _demo_answers(client, MIXED_DEMO)
    session_id = _create_demo(client, MIXED_DEMO)

    with client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
        seen = _drain(ws, answers)

    assert [item["requirement_id"] for item in seen["interrupt"]] == [
        "REQ-002",
        "REQ-005",
        "REQ-006",
    ]
    assert seen["done"]["stop_reason"] == "valid_package_complete"
    assert len(seen["package"]) == 1
    nodes = [item["node"] for item in seen["node_update"]]
    assert "parse_round" in nodes and "generate_final" in nodes

    view = client.get(f"/api/sessions/{session_id}").json()
    assert view["status"] == "completed"

    artifacts = client.get(f"/api/sessions/{session_id}/artifacts").json()
    names = set(artifacts["files"])
    assert {"agent_trace.json", "clarification_records.json", "prep_package.json"} <= names
    accepted = [item["accepted"] for item in artifacts["files"]["clarification_records.json"]]
    assert accepted == [True, False, True]


def test_artifacts_refused_before_completion(client):
    session_id = _create_demo(client, MIXED_DEMO)
    response = client.get(f"/api/sessions/{session_id}/artifacts")
    assert response.status_code == 409
    assert response.json()["error"]["category"] == "not_completed"


def test_demos_endpoint_lists_the_committed_scenarios(client):
    demos = client.get("/api/demos").json()["demos"]
    identifiers = {item["demo_id"] for item in demos}
    assert MIXED_DEMO in identifiers and COMPLETE_DEMO in identifiers


# --- bounds -------------------------------------------------------------------


def test_oversized_input_is_a_structured_413():
    settings = Settings(max_jd_chars=10)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/sessions",
            json={"mode": "demo", "jd_text": "x" * 11, "evidence_text": "y"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["category"] == "input_too_large"


def test_per_ip_session_cap_is_a_structured_429():
    settings = Settings(max_sessions_per_ip=1)
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/sessions", json={"mode": "demo", "demo_id": MIXED_DEMO})
        assert first.status_code == 201
        second = client.post("/api/sessions", json={"mode": "demo", "demo_id": MIXED_DEMO})
    assert second.status_code == 429
    assert second.json()["error"]["category"] == "per_ip_limit"


def test_live_mode_without_a_key_is_refused_at_creation(client):
    response = client.post(
        "/api/sessions",
        json={
            "mode": "live",
            "jd_text": "Requirements\n- SQL",
            "evidence_text": "- id: EV-001\n  summary: SQL work",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["category"] == "missing_credentials"


def test_unknown_demo_and_unknown_session_are_plain_refusals(client):
    assert (
        client.post("/api/sessions", json={"mode": "demo", "demo_id": "no-such-demo"}).status_code
        == 404
    )
    missing = client.get("/api/sessions/does-not-exist")
    assert missing.status_code == 404
    assert "expired" in missing.json()["error"]["message"]


# --- TTL ----------------------------------------------------------------------


def test_ttl_cleanup_evicts_expired_sessions(client):
    store = client.app.state.store
    session_id = _create_demo(client, MIXED_DEMO)
    store.get(session_id).created_at -= store.session_ttl_seconds + 1

    assert store.evict_expired() == 1
    assert store.active_count() == 0
    assert client.get(f"/api/sessions/{session_id}").status_code == 404


# --- credential hygiene -------------------------------------------------------

SECRET = "gm-key-TESTSECRET-3141"


def test_the_key_never_appears_in_logs_views_or_artifacts(client, caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "jd_text": "Requirements\n- Strong SQL for analysis",
                "evidence_text": "- id: EV-001\n  summary: SQL analysis work",
                "gemini_api_key": SECRET,
            },
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        view = client.get(f"/api/sessions/{session_id}").json()

    assert SECRET not in caplog.text
    assert SECRET not in response.text
    assert SECRET not in str(view)

    store = client.app.state.store
    session = store.get(session_id)
    assert session.api_key == SECRET  # held in memory for the provider
    for path in session.artifacts_dir.rglob("*"):
        assert SECRET not in path.read_text(encoding="utf-8")
    store.drop(session_id)
    assert session.api_key is None  # dropped with the session


# --- isolation ----------------------------------------------------------------


def test_two_concurrent_demo_sessions_do_not_share_state(client):
    answers = _demo_answers(client, MIXED_DEMO)
    mixed_id = _create_demo(client, MIXED_DEMO)
    complete_id = _create_demo(client, COMPLETE_DEMO)
    assert mixed_id != complete_id

    with client.websocket_connect(f"/api/sessions/{mixed_id}/stream") as first:
        # Reach the first interrupt, then leave the session waiting.
        while True:
            message = first.receive_json()
            if message["type"] == "interrupt":
                pending = message
                break

        # A second session runs to completion while the first is suspended.
        with client.websocket_connect(f"/api/sessions/{complete_id}/stream") as second:
            seen = _drain(second, {})
        assert seen["done"]["stop_reason"] == "valid_package_complete"
        assert seen["interrupt"] == []

        # The first session resumes exactly where it paused.
        first.send_json({"type": "answer", "text": answers[pending["requirement_id"]]})
        seen_first = _drain(first, answers)

    assert seen_first["done"]["stop_reason"] == "valid_package_complete"
    remaining = [item["requirement_id"] for item in seen_first["interrupt"]]
    assert remaining == ["REQ-005", "REQ-006"]

    first_records = client.get(f"/api/sessions/{mixed_id}/artifacts").json()["files"][
        "clarification_records.json"
    ]
    second_records = client.get(f"/api/sessions/{complete_id}/artifacts").json()["files"][
        "clarification_records.json"
    ]
    assert len(first_records) == 3
    assert second_records == []


# --- message hygiene ----------------------------------------------------------


def test_oversized_answer_is_refused_and_the_run_continues():
    settings = Settings(max_answer_chars=30)
    with TestClient(create_app(settings)) as client:
        answers = _demo_answers(client, MIXED_DEMO)
        session_id = _create_demo(client, MIXED_DEMO)
        with client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
            while True:
                message = ws.receive_json()
                if message["type"] == "interrupt":
                    break
            ws.send_json({"type": "answer", "text": "x" * 31})
            refusal = ws.receive_json()
            assert refusal["type"] == "error"
            assert refusal["category"] == "input_too_large"
            # The interrupt is still pending; a bounded answer resumes it.
            ws.send_json({"type": "answer", "text": answers[message["requirement_id"]][:30]})
            follow_up = ws.receive_json()
            assert follow_up["type"] in ("node_update", "interrupt")

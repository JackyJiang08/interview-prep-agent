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
        seen.setdefault(message["type"], []).append(message)
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
    evidence_ids = [item["id"] for item in seen["package"][0]["evidence"]]
    assert "CL-001" in evidence_ids  # the admitted claims ride with the package
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
SEARCH_SECRET = "tv-key-TESTSECRET-2718"


def test_the_key_never_appears_in_logs_views_or_artifacts(client, caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "jd_text": "Requirements\n- Strong SQL for analysis",
                "evidence_text": "- id: EV-001\n  summary: SQL analysis work",
                "gemini_api_key": SECRET,
                "tavily_api_key": SEARCH_SECRET,
            },
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        view = client.get(f"/api/sessions/{session_id}").json()

    for secret in (SECRET, SEARCH_SECRET):
        assert secret not in caplog.text
        assert secret not in response.text
        assert secret not in str(view)

    store = client.app.state.store
    session = store.get(session_id)
    assert session.api_key == SECRET  # held in memory for the providers
    assert session.search_api_key == SEARCH_SECRET
    for path in session.artifacts_dir.rglob("*"):
        content = path.read_text(encoding="utf-8")
        assert SECRET not in content and SEARCH_SECRET not in content
    store.drop(session_id)
    assert session.api_key is None  # dropped with the session
    assert session.search_api_key is None


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


# --- research plumbing --------------------------------------------------------


def test_research_text_is_accepted_in_both_modes(client):
    demo = client.post(
        "/api/sessions",
        json={
            "mode": "demo",
            "demo_id": MIXED_DEMO,
            "research_text": "A note about the reported screen themes.",
        },
    )
    assert demo.status_code == 201
    store = client.app.state.store
    session = store.get(demo.json()["session_id"])
    assert session.research_text.startswith("A note")


def test_oversized_research_text_is_a_structured_413():
    from interview_prep_agent.config import Settings
    from interview_prep_agent.server.app import create_app

    settings = Settings(max_research_chars=10)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/sessions",
            json={"mode": "demo", "demo_id": MIXED_DEMO, "research_text": "x" * 11},
        )
    assert response.status_code == 413
    assert response.json()["error"]["category"] == "input_too_large"


def test_package_event_carries_research_findings(client):
    answers = _demo_answers(client, MIXED_DEMO)
    created = client.post(
        "/api/sessions",
        json={
            "mode": "demo",
            "demo_id": MIXED_DEMO,
            "research_text": "Reported theme: experiment walkthroughs are common.",
        },
    )
    session_id = created.json()["session_id"]
    with client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
        seen = _drain(ws, answers)
    research = seen["package"][0]["research"]
    assert [item["finding_id"] for item in research] == ["SRC-001"]
    assert research[0]["source_kind"] == "provided"


# --- security headers ---------------------------------------------------------


def test_every_response_carries_the_security_headers(client):
    for path in ("/", "/api/health"):
        response = client.get(path)
        headers = response.headers
        assert headers["Strict-Transport-Security"] == "max-age=31536000"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_the_content_security_policy_matches_what_the_page_loads(client):
    for path in ("/", "/api/health"):
        policy = client.get(path).headers["Content-Security-Policy"]
        directives = dict(
            (part.split(" ", 1) + [""])[:2]
            for part in (item.strip() for item in policy.split(";"))
            if part
        )
        assert directives["default-src"] == "'self'"
        assert directives["script-src"] == "'self'"  # the built page has no inline script
        assert directives["style-src"] == "'self'"
        # The session socket shares the host but not the scheme, so the ws
        # and wss origins are named next to 'self'.
        connect = directives["connect-src"].split()
        assert "'self'" in connect
        assert "ws://testserver" in connect and "wss://testserver" in connect
        assert directives["frame-ancestors"] == "'none'"


# --- evidence preview ---------------------------------------------------------


def test_preview_reports_the_count_and_first_summaries(client):
    response = client.post(
        "/api/preview-evidence",
        json={
            "evidence_text": (
                "## Work\n\n- First achievement here\n- Second achievement here\n"
                "- Third one\n- Fourth one\n"
            ),
            "evidence_format": "markdown",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 4
    assert body["summaries"] == ["First achievement here", "Second achievement here", "Third one"]


def test_preview_reads_a_yaml_corpus_too(client):
    response = client.post(
        "/api/preview-evidence",
        json={"evidence_text": "- id: EV-001\n  summary: SQL work\n", "evidence_format": "yaml"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_preview_refuses_empty_and_unreadable_text_with_a_category(client):
    blank = client.post("/api/preview-evidence", json={"evidence_text": "   \n"})
    assert blank.status_code == 422
    assert blank.json()["error"]["category"] == "empty_evidence"

    furniture = client.post("/api/preview-evidence", json={"evidence_text": "Page 1 of 1\n---\n"})
    assert furniture.status_code == 422
    body = furniture.json()["error"]
    assert body["category"] == "empty_evidence"
    assert "no readable content" in body["message"]

    broken = client.post(
        "/api/preview-evidence",
        json={
            "evidence_text": "- id: EV-001\n  summary: SQL\n- id: EV-001\n  summary: dup\n",
            "evidence_format": "yaml",
        },
    )
    assert broken.status_code == 422
    assert broken.json()["error"]["category"] == "invalid_evidence"


def test_preview_honors_the_evidence_ceiling():
    with TestClient(create_app(Settings(max_evidence_chars=10))) as client:
        response = client.post("/api/preview-evidence", json={"evidence_text": "x" * 11})
    assert response.status_code == 413


# --- progress -----------------------------------------------------------------


def test_progress_events_name_the_stages_in_order_inside_each_generation(client):
    answers = _demo_answers(client, COMPLETE_DEMO)
    session_id = _create_demo(client, COMPLETE_DEMO)
    with client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
        seen = _drain(ws, answers)
    progress = seen["progress"]
    stages = [item["stage"] for item in progress]
    # One full pass per generation: the complete profile asks nothing, so
    # there are exactly two, each in graph order.
    expected = [
        "extract_evidence",
        "extract_requirements",
        "match",
        "assess_gaps",
        "research",
        "build_strategy",
        "generate_questions",
        "validate_package",
    ]
    assert stages == expected * 2
    assert [item["index"] for item in progress[:8]] == list(range(1, 9))
    assert {item["total"] for item in progress} == {8}

"""Skipping questions, closing the queue, crafted wording, and the ceiling."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from interview_prep_agent.agent import (
    SKIP_ANSWER,
    SKIP_REMAINING_ANSWER,
    STOP_VALID_PACKAGE,
    build_question,
    craft_question,
    run_agent,
)
from interview_prep_agent.config import Settings
from interview_prep_agent.models import CoverageLevel, Requirement
from interview_prep_agent.server.app import create_app

_spec = importlib.util.spec_from_file_location(
    "trajectories", Path(__file__).with_name("test_agent_trajectories.py")
)
trajectories = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trajectories)


def _run(answer_for):
    provider = trajectories.ScriptedProvider()
    asked: list[tuple[str, str]] = []

    def ask_callback(requirement_id: str, question: str) -> str:
        asked.append((requirement_id, question))
        return answer_for(requirement_id, len(asked))

    state, trace = run_agent(
        trajectories.JOB_DESCRIPTION,
        trajectories.EVIDENCE_YAML,
        "corpus",
        ask_callback,
        Settings(),
        None,
        model=provider,
        extractor=trajectories.scripted_extractor,
    )
    return state, trace, provider, asked


def _gaps(state) -> set[str]:
    return {
        verdict.requirement_id
        for verdict in state["matches"]
        if verdict.coverage is CoverageLevel.GAP
    }


# --- skips --------------------------------------------------------------------


def test_skipping_every_question_yields_a_valid_package_with_every_gap_honest():
    state, trace, provider, asked = _run(lambda _rid, _n: SKIP_REMAINING_ANSWER)

    # One question was shown; closing the queue ended the asking.
    assert [rid for rid, _ in asked] == ["REQ-002"]
    assert state["stop_reason"] == STOP_VALID_PACKAGE
    assert state["package_valid"] is True
    assert state["questions_closed"] is True
    assert provider.workflow_runs == 2
    assert provider.assessments_requested == []  # no model saw a skip

    # Every gap is still a gap: nothing was admitted, nothing invented.
    assert _gaps(state) == {"REQ-002", "REQ-003", "REQ-004"}
    assert state.get("clarification_evidence", []) == []
    records = state["clarification_records"]
    assert [record.accepted for record in records] == [False]
    assert records[0].answer == ""
    assert "closed" in records[0].decision_reason
    assert [entry["node"] for entry in trace][-2:] == ["generate_final", "stop"]


def test_skipping_one_question_records_it_and_asks_the_rest():
    def answer_for(rid: str, _n: int) -> str:
        return SKIP_ANSWER if rid == "REQ-003" else trajectories.ANSWERS[rid]

    state, _trace, provider, asked = _run(answer_for)
    assert [rid for rid, _ in asked] == ["REQ-002", "REQ-003", "REQ-004"]
    records = {record.requirement_id: record for record in state["clarification_records"]}
    assert records["REQ-003"].accepted is False
    assert "no answer was given" in records["REQ-003"].decision_reason
    assert records["REQ-002"].accepted is True
    assert records["REQ-004"].accepted is True
    assert "REQ-003" not in provider.assessments_requested
    assert "REQ-003" in _gaps(state)
    assert state["stop_reason"] == STOP_VALID_PACKAGE


# --- crafted wording ----------------------------------------------------------


GAP = Requirement(
    id="REQ-002",
    text="Designing controlled experiments for product decisions",
    normalized="designing controlled experiments",
    source_quote="Designing controlled experiments for product decisions",
)


class CraftingProvider(trajectories.ScriptedProvider):
    def __init__(self, crafted: Any) -> None:
        super().__init__()
        self.crafted = crafted

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        if "question" in response_schema.get("properties", {}) and "requirement_id" not in (
            response_schema.get("properties", {})
        ):
            if isinstance(self.crafted, Exception):
                raise self.crafted
            return self.crafted
        return super().generate_json(prompt, response_schema)


def test_a_crafted_question_replaces_the_template_wording_only():
    crafted = craft_question(
        GAP,
        "posting",
        CraftingProvider({"question": "Walk me through one experiment you designed."}),
    )
    assert crafted == "Walk me through one experiment you designed."


def test_any_crafting_failure_falls_back_to_the_template():
    template = build_question(GAP)
    assert craft_question(GAP, "posting", CraftingProvider(RuntimeError("down"))) == template
    assert craft_question(GAP, "posting", CraftingProvider({"wrong": "shape"})) == template
    assert craft_question(GAP, "posting", CraftingProvider({"question": "   "})) == template


def test_fixture_runs_keep_the_template_and_live_runs_craft():
    def answer_for(rid: str, _n: int) -> str:
        return trajectories.ANSWERS[rid]

    provider = CraftingProvider({"question": "A crafted question?"})
    asked: list[str] = []

    def ask_callback(_rid: str, question: str) -> str:
        asked.append(question)
        return answer_for(_rid, 0)

    for craft, expected in ((False, build_question(GAP)), (True, "A crafted question?")):
        asked.clear()
        run_agent(
            trajectories.JOB_DESCRIPTION,
            trajectories.EVIDENCE_YAML,
            "corpus",
            ask_callback,
            Settings(),
            None,
            model=provider,
            extractor=trajectories.scripted_extractor,
            craft_questions=craft,
        )
        assert asked[0] == expected


# --- the ceiling, over the server ----------------------------------------------


def test_a_live_session_stops_asking_at_its_ceiling(monkeypatch):
    import test_server_live_stages as live

    provider = live.ScriptedLiveProvider()
    monkeypatch.setattr("interview_prep_agent.providers.build_model", lambda *a, **k: provider)
    with TestClient(create_app(Settings())) as client:
        _view, run = live._run_live(client, max_questions=0)
    assert run["seen"]["interrupt"] == []
    final = next(item for item in run["seen"]["node_update"] if item["node"] == "generate_final")
    assert final["delta"]["package_valid"] is True
    assert "ceiling" in final["delta"].get("note", "")


def test_the_skip_messages_work_over_the_socket():
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/sessions", json={"mode": "demo", "demo_id": "mixed-clarifications"}
        )
        session_id = response.json()["session_id"]
        interrupts: list[dict] = []
        records: list[dict] = []
        with client.websocket_connect(f"/api/sessions/{session_id}/stream") as ws:
            while True:
                message = ws.receive_json()
                if message["type"] == "done":
                    assert message["stop_reason"] == STOP_VALID_PACKAGE
                    break
                if message["type"] == "interrupt":
                    interrupts.append(message)
                    assert message["requirement_text"]  # the requirement rides along
                    ws.send_json({"type": "skip" if len(interrupts) == 1 else "skip_remaining"})
                if message["type"] == "node_update" and "record" in message["delta"]:
                    records.append(message["delta"]["record"])
    # Three gaps; one skipped, then the queue closed on the second.
    assert [item["requirement_id"] for item in interrupts] == ["REQ-002", "REQ-005"]
    assert [item["accepted"] for item in records] == [False, False]

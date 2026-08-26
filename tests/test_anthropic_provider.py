"""The third provider, with the vendor client mocked."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from interview_prep_agent.config import Settings
from interview_prep_agent.models import InterviewRound
from interview_prep_agent.providers import PROVIDERS, ProviderError, build_model
from interview_prep_agent.providers.anthropic import DEFAULT_MODEL, AnthropicModel
from interview_prep_agent.providers.schema import close_schema
from interview_prep_agent.server.app import create_app

KEY = "an-key-TESTSECRET-2718"


class FakeMessages:
    """Records the request and returns a scripted message."""

    def __init__(self, content: str | None, stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = [] if self.content is None else [SimpleNamespace(type="text", text=self.content)]
        return SimpleNamespace(content=blocks, stop_reason=self.stop_reason)


def build_fake_model(
    monkeypatch, content: str | None, stop_reason: str = "end_turn"
) -> tuple[AnthropicModel, FakeMessages]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    model = AnthropicModel()
    messages = FakeMessages(content, stop_reason)
    model._client = SimpleNamespace(messages=messages)  # noqa: SLF001 - substituting the vendor client
    return model, messages


# --- construction -------------------------------------------------------------


def test_missing_key_fails_in_the_established_style(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY is not set"):
        build_model("anthropic")


def test_anthropic_is_a_registered_provider():
    assert "anthropic" in PROVIDERS


def test_the_model_name_defaults_and_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert AnthropicModel().name == DEFAULT_MODEL
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-from-env")
    assert AnthropicModel().name == "claude-from-env"
    assert AnthropicModel(model="claude-explicit").name == "claude-explicit"


def test_the_client_is_built_lazily(monkeypatch):
    # Construction resolves the key and nothing else: no SDK import, no client.
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    model = AnthropicModel()
    assert model._client is None  # noqa: SLF001
    assert "anthropic" not in sys.modules


# --- the request --------------------------------------------------------------


def test_the_schema_is_requested_as_the_output_format(monkeypatch):
    schema = InterviewRound.model_json_schema()
    model, messages = build_fake_model(monkeypatch, json.dumps({"round_type": "technical screen"}))

    payload = model.generate_json("a prompt", schema)

    assert payload == {"round_type": "technical screen"}
    request = messages.calls[0]
    assert request["model"] == DEFAULT_MODEL
    assert request["messages"] == [{"role": "user", "content": "a prompt"}]
    output_format = request["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["additionalProperties"] is False
    assert set(output_format["schema"]["required"]) == set(schema["properties"])


def test_the_closed_schema_is_the_shared_adaptation():
    schema = close_schema(InterviewRound.model_json_schema())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


def test_malformed_json_raises(monkeypatch):
    model, _ = build_fake_model(monkeypatch, "not json at all")
    with pytest.raises(ProviderError, match="unparseable JSON"):
        model.generate_json("a prompt", InterviewRound.model_json_schema())


def test_empty_content_raises(monkeypatch):
    model, _ = build_fake_model(monkeypatch, None)
    with pytest.raises(ProviderError, match="no content"):
        model.generate_json("a prompt", InterviewRound.model_json_schema())


def test_a_declined_request_raises(monkeypatch):
    model, _ = build_fake_model(monkeypatch, "{}", stop_reason="refusal")
    with pytest.raises(ProviderError, match="declined"):
        model.generate_json("a prompt", InterviewRound.model_json_schema())


def test_a_failing_request_raises_a_provider_error(monkeypatch):
    model, messages = build_fake_model(monkeypatch, "{}")

    def explode(**_kwargs):
        raise RuntimeError("the model is unavailable")

    messages.create = explode
    with pytest.raises(ProviderError, match="Anthropic request failed"):
        model.generate_json("a prompt", InterviewRound.model_json_schema())


# --- selection plumbs through -------------------------------------------------


def test_cli_commands_accept_the_provider_flag():
    from interview_prep_agent.cli import build_parser

    for command in ("prep", "agent"):
        args = build_parser().parse_args(
            [command, "--jd", "a", "--evidence", "b.yaml", "--provider", "anthropic"]
        )
        assert args.provider == "anthropic"
    evaluation = build_parser().parse_args(["eval", "--suite", "live", "--provider", "anthropic"])
    assert evaluation.provider == "anthropic"


def test_the_live_suite_names_the_missing_key(monkeypatch):
    from interview_prep_agent.evals.runner import _require_environment

    monkeypatch.setenv("LANGSMITH_API_KEY", "ls")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _require_environment("live", provider="anthropic")


def test_server_live_anthropic_without_a_key_is_refused():
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "provider": "anthropic",
                "jd_text": "Requirements\n- SQL",
                "evidence_text": "- id: EV-001\n  summary: SQL work",
                "gemini_api_key": "the wrong provider's key",
            },
        )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["category"] == "missing_credentials"
    assert "anthropic_api_key" in body["message"]


def test_server_stores_the_anthropic_key_in_memory_only_and_drops_it():
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "provider": "anthropic",
                "jd_text": "Requirements\n- SQL",
                "evidence_text": "- id: EV-001\n  summary: SQL work",
                "anthropic_api_key": KEY,
            },
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        view = client.get(f"/api/sessions/{session_id}").json()
        assert KEY not in response.text
        assert KEY not in str(view)
        assert view["provider"] == "anthropic"

        store = client.app.state.store
        session = store.get(session_id)
        assert session.api_key == KEY
        store.drop(session_id)
        assert session.api_key is None


def test_health_lists_all_three_providers():
    with TestClient(create_app(Settings())) as client:
        payload = client.get("/api/health").json()
    assert payload["version"] == "0.4.0"
    assert payload["modes"]["live"]["providers"] == ["gemini", "azure", "anthropic"]

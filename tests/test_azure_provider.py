"""The second provider, with the vendor client mocked."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from interview_prep_agent.config import Settings
from interview_prep_agent.models import InterviewRound
from interview_prep_agent.providers import PROVIDERS, ProviderError, build_model
from interview_prep_agent.providers.azure import AzureOpenAIModel, _strict_schema
from interview_prep_agent.server.app import create_app

AZURE_ENV = {
    "AZURE_OPENAI_API_KEY": "az-key-TESTSECRET-1618",
    "AZURE_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com",
    "AZURE_OPENAI_DEPLOYMENT": "a-deployment",
}


class FakeCompletions:
    """Records the request and returns a scripted assistant message."""

    def __init__(self, content: str | None) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def build_fake_model(monkeypatch, content: str | None) -> tuple[AzureOpenAIModel, FakeCompletions]:
    for name, value in AZURE_ENV.items():
        monkeypatch.setenv(name, value)
    model = AzureOpenAIModel()
    completions = FakeCompletions(content)
    model._client = SimpleNamespace(  # noqa: SLF001 - substituting the vendor client
        chat=SimpleNamespace(completions=completions)
    )
    return model, completions


# --- construction -------------------------------------------------------------


def test_missing_configuration_fails_in_the_established_style(monkeypatch):
    for name in AZURE_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ProviderError, match="is not set"):
        build_model("azure")


def test_partial_configuration_names_every_missing_setting(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    with pytest.raises(ProviderError) as excinfo:
        build_model("azure")
    message = str(excinfo.value)
    assert "AZURE_OPENAI_ENDPOINT" in message
    assert "AZURE_OPENAI_DEPLOYMENT" in message
    assert "AZURE_OPENAI_API_KEY" not in message


def test_azure_is_a_registered_provider():
    assert "azure" in PROVIDERS


def test_the_deployment_is_the_reported_name(monkeypatch):
    model, _ = build_fake_model(monkeypatch, "{}")
    assert model.name == "a-deployment"


# --- the request --------------------------------------------------------------


def test_the_schema_is_requested_strictly(monkeypatch):
    schema = InterviewRound.model_json_schema()
    model, completions = build_fake_model(
        monkeypatch, json.dumps({"round_type": "technical screen"})
    )

    payload = model.generate_json("a prompt", schema)

    assert payload == {"round_type": "technical screen"}
    request = completions.calls[0]
    assert request["model"] == "a-deployment"
    assert request["messages"][0]["content"] == "a prompt"
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False


def test_strict_schema_requires_every_property():
    schema = _strict_schema(InterviewRound.model_json_schema())
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


def test_a_failing_request_raises_a_provider_error(monkeypatch):
    model, completions = build_fake_model(monkeypatch, "{}")

    def explode(**_kwargs):
        raise RuntimeError("the deployment is unavailable")

    completions.create = explode
    with pytest.raises(ProviderError, match="Azure OpenAI request failed"):
        model.generate_json("a prompt", InterviewRound.model_json_schema())


# --- selection plumbs through -------------------------------------------------


def test_cli_commands_accept_the_provider_flag():
    from interview_prep_agent.cli import build_parser

    for command in ("prep", "agent"):
        args = build_parser().parse_args(
            [command, "--jd", "a", "--evidence", "b.yaml", "--provider", "azure"]
        )
        assert args.provider == "azure"
    evaluation = build_parser().parse_args(["eval", "--suite", "live", "--provider", "azure"])
    assert evaluation.provider == "azure"


def test_cli_rejects_an_unknown_provider():
    from interview_prep_agent.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["prep", "--jd", "a", "--evidence", "b.yaml", "--provider", "nowhere"]
        )


def test_server_live_azure_requires_every_setting():
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "provider": "azure",
                "jd_text": "Requirements\n- SQL",
                "evidence_text": "- id: EV-001\n  summary: SQL work",
                "azure_api_key": "k",
            },
        )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["category"] == "missing_credentials"
    assert "azure_endpoint" in body["message"]
    assert "azure_deployment" in body["message"]


def test_server_stores_azure_credentials_in_memory_only_and_drops_them():
    secret = "az-key-TESTSECRET-2236"
    with TestClient(create_app(Settings())) as client:
        response = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "provider": "azure",
                "jd_text": "Requirements\n- SQL",
                "evidence_text": "- id: EV-001\n  summary: SQL work",
                "azure_api_key": secret,
                "azure_endpoint": "https://example-resource.openai.azure.com",
                "azure_deployment": "a-deployment",
            },
        )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        view = client.get(f"/api/sessions/{session_id}").json()
        assert secret not in response.text
        assert secret not in str(view)
        assert view["provider"] == "azure"

        store = client.app.state.store
        session = store.get(session_id)
        assert session.api_key == secret
        assert session.azure_deployment == "a-deployment"
        store.drop(session_id)
        assert session.api_key is None
        assert session.azure_endpoint is None
        assert session.azure_deployment is None


def test_health_reports_version_and_capabilities():
    with TestClient(create_app(Settings())) as client:
        payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["modes"]["demo"] is True
    assert payload["modes"]["live"]["server_side_credentials"] is False
    assert set(payload["modes"]["live"]["providers"]) == set(PROVIDERS)

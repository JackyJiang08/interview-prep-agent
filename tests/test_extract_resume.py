"""PDF resume intake: extraction, normalization, refusals, and the full path."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_prep_agent.config import Settings
from interview_prep_agent.corpus import parse_evidence_markdown
from interview_prep_agent.server.app import create_app
from interview_prep_agent.server.extract import (
    ExtractionRefused,
    extract_resume,
    normalize_resume_text,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_PDF = FIXTURES / "resume_synthetic.pdf"

_spec = importlib.util.spec_from_file_location("make_resume_pdf", FIXTURES / "make_resume_pdf.py")
make_resume_pdf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_resume_pdf)


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def _post_pdf(client: TestClient, data: bytes, filename: str = "resume.pdf"):
    return client.post(
        "/api/extract-resume",
        json={"filename": filename, "content_base64": base64.b64encode(data).decode("ascii")},
    )


# --- the committed fixture ----------------------------------------------------


def test_the_fixture_is_what_the_generator_writes():
    # The committed bytes are a function of the generator, so a drift in
    # either is a signal rather than a silent difference.
    assert FIXTURE_PDF.read_bytes() == make_resume_pdf.build_pdf(make_resume_pdf.RESUME_PAGES)


def test_extraction_keeps_headings_and_bullets_and_drops_furniture():
    text, pages = extract_resume(FIXTURE_PDF.read_bytes())
    assert pages == 2
    assert "## EXPERIENCE" in text
    assert "## Skills" in text
    assert "- Owned funnel analysis for a subscription product, writing SQL" in text
    assert "  against a warehouse of roughly 40 million events." in text
    assert "Page 1 of 2" not in text and "Page 2 of 2" not in text


def test_the_extracted_text_is_a_resume_the_corpus_reader_accepts():
    text, _ = extract_resume(FIXTURE_PDF.read_bytes())
    items = parse_evidence_markdown(text)
    assert [item.id for item in items] == ["EV-001", "EV-002", "EV-003", "EV-004"]
    assert items[0].summary.startswith("Owned funnel analysis")
    assert items[0].summary.endswith("40 million events.")  # the wrapped line rejoined
    assert items[0].source == "EXPERIENCE / Data Analyst, Example Co. (2022 - present)"
    assert items[2].source == "Skills"


def test_normalization_drops_lines_that_recur_on_every_page():
    pages = [
        "Jordan Example\nSummary\n• Did a thing.\nPage 1",
        "Jordan Example\n• Did another thing.\nPage 2",
    ]
    text = normalize_resume_text(pages)
    assert "Jordan Example" not in text
    assert "Page 1" not in text and "Page 2" not in text
    assert text == "## Summary\n\n- Did a thing.\n- Did another thing.\n"


# --- refusals -----------------------------------------------------------------


def test_a_pdf_without_a_text_layer_is_refused_with_advice(client):
    scan = make_resume_pdf.build_pdf([[]])
    with pytest.raises(ExtractionRefused) as excinfo:
        extract_resume(scan)
    assert excinfo.value.category == "no_text_layer"

    response = _post_pdf(client, scan)
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["category"] == "no_text_layer"
    assert "paste the resume text instead" in body["message"]


def test_bytes_that_are_not_a_pdf_are_refused(client):
    response = _post_pdf(client, b"this is not a pdf at all")
    assert response.status_code == 422
    assert response.json()["error"]["category"] == "unreadable_pdf"


def test_the_size_cap_is_a_structured_413():
    with TestClient(create_app(Settings(max_resume_pdf_bytes=100))) as client:
        response = _post_pdf(client, FIXTURE_PDF.read_bytes())
    assert response.status_code == 413
    body = response.json()["error"]
    assert body["category"] == "input_too_large"
    assert "100-byte ceiling" in body["message"]


def test_the_extension_check_is_case_insensitive(client):
    upper = _post_pdf(client, FIXTURE_PDF.read_bytes(), filename="RESUME.PDF")
    assert upper.status_code == 200
    assert upper.json()["pages"] == 2
    other = _post_pdf(client, FIXTURE_PDF.read_bytes(), filename="resume.docx")
    assert other.status_code == 400
    assert other.json()["error"]["category"] == "unsupported_file"


def test_invalid_base64_is_a_plain_refusal(client):
    response = client.post(
        "/api/extract-resume", json={"filename": "resume.pdf", "content_base64": "not base64!!"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["category"] == "bad_encoding"


# --- the whole path -----------------------------------------------------------


def test_drop_extract_preview_then_start_a_session(client):
    # Drop: the browser sends the file's bytes.
    extracted = _post_pdf(client, FIXTURE_PDF.read_bytes())
    assert extracted.status_code == 200
    preview = extracted.json()["text"]
    assert extracted.json()["characters"] == len(preview)

    # Preview: the visitor corrects one line before starting.
    corrected = preview.replace("40 million events", "42 million events")

    # Start: the corrected text is ordinary evidence text on the session.
    response = client.post(
        "/api/sessions",
        json={
            "mode": "live",
            "jd_text": "Requirements\n- SQL against a large warehouse",
            "evidence_text": corrected,
            "evidence_format": "markdown",
            "gemini_api_key": "gm-key-TESTSECRET-0001",
        },
    )
    assert response.status_code == 201
    session = client.app.state.store.get(response.json()["session_id"])
    assert session.evidence_format == "markdown"
    assert "42 million events" in session.evidence_source
    assert len(parse_evidence_markdown(session.evidence_source)) == 4

"""The deterministic guard after extraction: drops with reasons, never silent."""

from __future__ import annotations

from interview_prep_agent.models import Requirement
from interview_prep_agent.workflow.graph import build_workflow
from interview_prep_agent.workflow.guard import drop_reason, guard_requirements


def _requirement(number: int, text: str) -> Requirement:
    return Requirement(
        id=f"REQ-{number:03d}", text=text, normalized=text.casefold(), source_quote=text
    )


# The shapes a real run extracted from a real posting and asked about as gaps.
JUNK = [
    "Job description",
    "Location",
    "Job Title",
    "Requirements:",
    "What you will do",
    "Salary range $90,000 to $120,000 per year depending on experience",
    "We are an equal opportunity employer and do not discriminate on any protected status.",
    "SQL",
]
REAL = [
    "Strong SQL and Python for analysis on large datasets",
    "Designing controlled experiments for product decisions",
    "Presenting recommendations to senior leadership",
    "AWS or GCP experience in production",
]


def test_headings_disclaimers_and_fragments_are_dropped_with_a_reason():
    reasons = {text: drop_reason(text, min_chars=12) for text in JUNK}
    assert reasons["Job description"] == "reads as a section heading"
    assert reasons["Location"] == "reads as a section heading"
    assert reasons["Job Title"] == "reads as a section heading"
    assert reasons["Requirements:"] == "reads as a section heading"
    assert reasons["What you will do"] == "reads as a section heading"
    assert "salary" in reasons["Salary range $90,000 to $120,000 per year depending on experience"]
    assert "equal-opportunity" in reasons[JUNK[6]]
    assert reasons["SQL"] == "shorter than 12 characters"


def test_real_requirements_pass_untouched():
    assert all(drop_reason(text, min_chars=12) is None for text in REAL)


def test_kept_items_are_renumbered_and_drops_carry_their_original_identifiers():
    mixed = [_requirement(1, JUNK[0]), _requirement(2, REAL[0]), _requirement(3, JUNK[5])]
    kept, dropped = guard_requirements(mixed, min_chars=12)
    assert [(item.id, item.text) for item in kept] == [("REQ-001", REAL[0])]
    assert [item["id"] for item in dropped] == ["REQ-001", "REQ-003"]
    assert all(set(item) == {"id", "text", "reason"} for item in dropped)


def test_the_graph_records_drops_in_state_rather_than_hiding_them():
    posting = "\n".join([*JUNK, *REAL])
    junk_and_real = [_requirement(n, text) for n, text in enumerate([*JUNK, *REAL], start=1)]
    workflow = build_workflow(extractor=lambda _text: junk_and_real, min_requirement_chars=12)
    state = workflow.invoke({"job_description": posting, "evidence": []})
    assert [item.text for item in state["requirements"]] == REAL
    assert [item.id for item in state["requirements"]] == [f"REQ-{n:03d}" for n in range(1, 5)]
    assert len(state["dropped_requirements"]) == len(JUNK)
    assert {item["text"] for item in state["dropped_requirements"]} == set(JUNK)


def test_the_floor_is_a_setting():
    assert drop_reason("Strong SQL", min_chars=0) is None
    assert drop_reason("Strong SQL", min_chars=20) == "shorter than 20 characters"

"""A stated company and role title reach research and preparation, nothing else."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interview_prep_agent.agent import build_round_parsing_prompt
from interview_prep_agent.config import Settings
from interview_prep_agent.models import (
    CoverageLevel,
    FocusArea,
    InterviewStrategy,
    Requirement,
    RequirementMatch,
    Status,
)
from interview_prep_agent.server.app import create_app
from interview_prep_agent.workflow.questions import QUESTION_INSTRUCTIONS, build_question_prompt
from interview_prep_agent.workflow.research import build_queries, gather_research, role_label
from interview_prep_agent.workflow.strategy import build_strategy_prompt

POSTING = "Senior Data Analyst - Example Co.\n\nRequirements\n- Strong SQL\n"
REQUIREMENT = Requirement(
    id="REQ-001",
    text="Strong SQL",
    normalized="strong sql",
    source_quote="Strong SQL",
    importance=4,
)


class RecordingSearch:
    name = "recording"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, max_results: int) -> list[dict]:
        self.queries.append(query)
        return [
            {
                "title": f"Result for {query}",
                "snippet": "A reported theme.",
                "url": f"https://example.org/{len(self.queries)}",
            }
        ]


# --- research queries ---------------------------------------------------------


def test_stated_company_and_role_replace_the_guessed_first_line():
    assert role_label(POSTING) == "Senior Data Analyst - Example Co."
    assert role_label(POSTING, "Example Co.", "Data Analyst") == "Data Analyst at Example Co."
    assert role_label(POSTING, "", "Data Analyst") == "Data Analyst"
    assert role_label(POSTING, "Example Co.", "") == "at Example Co."

    guessed = build_queries(POSTING, [REQUIREMENT], 3)
    stated = build_queries(
        POSTING, [REQUIREMENT], 3, company="Example Co.", role_title="Data Analyst"
    )
    assert guessed[0].startswith("Senior Data Analyst - Example Co. interview questions")
    assert stated == [
        "Data Analyst at Example Co. interview questions reported by candidates",
        "Data Analyst at Example Co. interview process and team",
        "Data Analyst at Example Co. interview Strong SQL",
    ]


def test_gather_research_issues_the_stated_queries():
    search = RecordingSearch()
    findings = gather_research(
        POSTING,
        [REQUIREMENT],
        "",
        search,
        max_queries=2,
        max_findings=12,
        company="Example Co.",
        role_title="Data Analyst",
    )
    assert search.queries == [
        "Data Analyst at Example Co. interview questions reported by candidates",
        "Data Analyst at Example Co. interview process and team",
    ]
    assert [item.finding_id for item in findings] == ["SRC-001", "SRC-002"]


# --- prompts ------------------------------------------------------------------


def _match() -> RequirementMatch:
    return RequirementMatch(
        requirement_id="REQ-001",
        status=Status.GAP,
        coverage=CoverageLevel.GAP,
        matches=[],
        method="lexical-idf-v1",
    )


def test_the_role_section_reaches_both_preparation_prompts_only_when_stated():
    focus = [
        FocusArea(
            requirement_id="REQ-001",
            coverage=CoverageLevel.GAP,
            priority=1,
            preparation_action="Prepare an honest answer.",
            reason="No evidence covers it.",
        )
    ]
    strategy = InterviewStrategy(
        top_priorities=[],
        positioning_statement="Grounded.",
        stories_to_prepare=[],
        risks_to_address=[],
    )
    without = build_strategy_prompt([REQUIREMENT], [_match()], focus)
    assert "----- ROLE -----" not in without
    with_role = build_strategy_prompt(
        [REQUIREMENT], [_match()], focus, company="Example Co.", role_title="Data Analyst"
    )
    assert "----- ROLE -----" in with_role
    assert '"company": "Example Co."' in with_role
    assert '"role_title": "Data Analyst"' in with_role
    # The role section sits before the round and research sections.
    assert with_role.index("----- ROLE -----") > with_role.index("----- FOCUS AREAS -----")

    questions = build_question_prompt(
        [REQUIREMENT], [_match()], strategy, company="Example Co.", role_title="Data Analyst"
    )
    assert "----- ROLE -----" in questions
    assert "reportedly asked" in QUESTION_INSTRUCTIONS
    assert "cite the finding's SRC- identifier" in QUESTION_INSTRUCTIONS


def test_the_round_parser_sees_the_role_as_context_before_the_description():
    plain = build_round_parsing_prompt("A 45-minute technical screen.")
    assert "----- ROLE -----" not in plain
    prompt = build_round_parsing_prompt(
        "A 45-minute technical screen.", "Example Co.", "Data Analyst"
    )
    assert "The candidate is interviewing for: Data Analyst at Example Co." in prompt
    assert prompt.index("----- ROLE -----") < prompt.index("----- ROUND DESCRIPTION -----")


# --- the server ---------------------------------------------------------------


def test_the_session_carries_the_fields_and_refuses_oversized_ones():
    with TestClient(create_app(Settings(max_role_field_chars=20))) as client:
        created = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "jd_text": POSTING,
                "evidence_text": "- id: EV-001\n  summary: SQL work",
                "gemini_api_key": "k",
                "company": "  Example Co. ",
                "role_title": "Data Analyst",
            },
        )
        assert created.status_code == 201
        session = client.app.state.store.get(created.json()["session_id"])
        assert (session.company, session.role_title) == ("Example Co.", "Data Analyst")

        refused = client.post(
            "/api/sessions",
            json={
                "mode": "live",
                "jd_text": POSTING,
                "evidence_text": "- id: EV-001\n  summary: SQL work",
                "gemini_api_key": "k",
                "company": "x" * 21,
            },
        )
    assert refused.status_code == 413
    assert "company exceeds the 20-character ceiling" in refused.json()["error"]["message"]

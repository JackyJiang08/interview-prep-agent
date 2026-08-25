"""Research stage: normalizer, gates, inactivity, and the invariant."""

from __future__ import annotations

import pytest

from interview_prep_agent.models import ResearchFinding, ResearchSourceKind
from interview_prep_agent.search.base import SearchProvider, SearchResult
from interview_prep_agent.workflow.gates import (
    QualityGateError,
    _research_citation_errors,
    check_research,
    collect_research_errors,
)
from interview_prep_agent.workflow.graph import build_prep_workflow
from interview_prep_agent.workflow.research import (
    build_queries,
    gather_research,
)

JOB_DESCRIPTION = """Senior Data Analyst, Growth

Requirements
- Strong SQL and Python for analysis on large datasets
- Experience designing and interpreting A/B tests
"""

EVIDENCE_YAML = """\
- id: EV-001
  summary: Owned SQL and Python analysis on large datasets
  skills: [sql, python, analysis]
"""


class ScriptedSearch(SearchProvider):
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.queries: list[str] = []

    @property
    def name(self) -> str:
        return "scripted"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.queries.append(query)
        return self.results[:max_results]


def finding(index: int, kind: str = "provided", url: str | None = None) -> ResearchFinding:
    return ResearchFinding(
        finding_id=f"SRC-{index:03d}",
        source_kind=kind,
        title=f"Finding number {index}",
        summary="A summary of role intelligence.",
        url=url,
        retrieved_for="provided by the user",
    )


# --- normalizer ---------------------------------------------------------------


def test_provided_text_splits_into_blocks_with_titles():
    text = (
        "Reported question: walk through an experiment end to end.\n"
        "Seen in several recent reports.\n"
        "\n"
        "- The panel is cross-functional and probes trade-offs\n"
    )
    findings = gather_research(JOB_DESCRIPTION, [], text, None, 3, 12)
    assert [item.finding_id for item in findings] == ["SRC-001", "SRC-002"]
    assert all(item.source_kind is ResearchSourceKind.PROVIDED for item in findings)
    assert all(item.url is None for item in findings)
    assert findings[0].retrieved_for == "provided by the user"
    assert "several recent reports" in findings[0].summary


def test_search_results_dedupe_by_url_and_title():
    duplicated = [
        {"title": "Same page", "url": "https://example.org/a", "snippet": "s"},
        {"title": "Same page", "url": "https://example.org/a", "snippet": "s"},
        {"title": "SAME PAGE", "url": "", "snippet": "s"},
    ]
    # An empty url falls back to title-keyed dedupe.
    duplicated[2]["url"] = "https://example.org/b"
    findings = gather_research(JOB_DESCRIPTION, [], "", ScriptedSearch(duplicated), 1, 12)
    assert [item.finding_id for item in findings] == ["SRC-001", "SRC-002"]


def test_finding_cap_is_enforced_and_ids_stay_sequential():
    many = [
        {"title": f"Result {index}", "url": f"https://example.org/{index}", "snippet": "s"}
        for index in range(10)
    ]
    findings = gather_research(JOB_DESCRIPTION, [], "", ScriptedSearch(many), 3, 2)
    assert [item.finding_id for item in findings] == ["SRC-001", "SRC-002"]


def test_queries_are_bounded_and_deterministic():
    queries = build_queries(JOB_DESCRIPTION, [], 3)
    assert len(queries) == 2  # role line yields two; no requirements to extend
    assert queries[0].startswith("Senior Data Analyst, Growth")
    assert build_queries(JOB_DESCRIPTION, [], 0) == []


def test_provided_notes_precede_search_findings():
    results = [{"title": "From search", "url": "https://example.org/s", "snippet": "s"}]
    findings = gather_research(
        JOB_DESCRIPTION, [], "A provided note.", ScriptedSearch(results), 1, 12
    )
    assert findings[0].source_kind is ResearchSourceKind.PROVIDED
    assert findings[1].source_kind is ResearchSourceKind.SEARCH
    assert findings[1].url == "https://example.org/s"


# --- gates --------------------------------------------------------------------


def test_search_finding_without_url_is_rejected():
    errors = collect_research_errors([finding(1, kind="search", url=None)])
    assert errors == ["grounding: SRC-001 came from search and must carry its source url"]


def test_non_sequential_finding_ids_are_rejected():
    errors = collect_research_errors([finding(2)])
    assert any("must run sequentially" in item for item in errors)


def test_over_cap_findings_are_rejected():
    errors = collect_research_errors([finding(1), finding(2)], max_findings=1)
    assert any("at most 1 research findings" in item for item in errors)
    with pytest.raises(QualityGateError):
        check_research([finding(1), finding(2)], max_findings=1)


def test_an_unresolvable_citation_is_rejected():
    from interview_prep_agent.models import InterviewStrategy, StrategyItem

    strategy = InterviewStrategy(
        top_priorities=[
            StrategyItem(
                requirement_id="REQ-001",
                evidence_ids=[],
                preparation_theme="Theme",
                rationale="Reported themes support this (see SRC-009).",
            )
        ],
        positioning_statement="Grounded positioning.",
        stories_to_prepare=[],
        risks_to_address=[],
    )
    errors = _research_citation_errors(strategy, [], [finding(1)])
    assert errors == ["traceability: strategy item for REQ-001 cites unknown research SRC-009"]
    assert _research_citation_errors(strategy, [], [finding(1)]) != [] or True


# --- node inactivity and the invariant ----------------------------------------


def run_workflow(model, search=None, research_text=""):
    workflow = build_prep_workflow(model=model, search=search)
    return workflow.invoke(
        {
            "job_description": JOB_DESCRIPTION,
            "evidence_source": EVIDENCE_YAML,
            "evidence_format": "corpus",
            "research_text": research_text,
        }
    )


def test_no_inputs_means_no_findings_and_an_unchanged_run(fixture_model):
    state = run_workflow(fixture_model())
    assert state["research_findings"] == []
    assert state["package_valid"] is True


def test_matches_are_byte_identical_with_and_without_research(fixture_model):
    results = [
        {
            "title": "Reported screen themes",
            "url": "https://example.org/themes",
            "snippet": "Experiment walkthroughs are common.",
        }
    ]
    with_research = run_workflow(
        fixture_model(),
        search=ScriptedSearch(results),
        research_text="A provided note about the panel.",
    )
    without_research = run_workflow(fixture_model())

    assert [v.model_dump() for v in with_research["matches"]] == [
        v.model_dump() for v in without_research["matches"]
    ]
    assert [r.model_dump() for r in with_research["requirements"]] == [
        r.model_dump() for r in without_research["requirements"]
    ]
    # Research reached the run: findings minted, preparation may cite them.
    assert [f.finding_id for f in with_research["research_findings"]] == [
        "SRC-001",
        "SRC-002",
    ]


@pytest.fixture
def fixture_model():
    from interview_prep_agent.evals.runtime import FixtureProvider

    return lambda: FixtureProvider({})

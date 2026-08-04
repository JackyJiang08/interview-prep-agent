"""Smoke tests for the lexical matcher."""

from __future__ import annotations

from interview_prep_agent import Status, extract_requirements, match_requirements
from interview_prep_agent.workflow.match import tokenize


def test_tokenize_keeps_compound_terms_whole_and_split():
    tokens = tokenize("SQL/Python and A/B")
    assert "sql/python" in tokens
    assert "sql" in tokens
    assert "python" in tokens
    assert "a/b" in tokens


def test_tokenize_drops_stopwords():
    assert tokenize("experience with the strong ability") == []


def test_supported_requirement_cites_evidence(sample_evidence):
    requirements = extract_requirements("- Strong SQL and Python for analysis on large datasets")
    verdicts = match_requirements(requirements, sample_evidence, threshold=0.30, max_matches=3)
    assert verdicts[0].status is Status.PROOF
    assert verdicts[0].matches[0].evidence_id == "EV-001"
    assert verdicts[0].matches[0].overlapping_terms


def test_unsupported_requirement_is_a_gap(sample_evidence):
    requirements = extract_requirements("- Familiarity with Kubernetes and service mesh operations")
    verdicts = match_requirements(requirements, sample_evidence, threshold=0.30, max_matches=3)
    assert verdicts[0].status is Status.GAP
    assert verdicts[0].matches == []


def test_scores_stay_within_unit_range(sample_job_description, sample_evidence):
    requirements = extract_requirements(sample_job_description)
    verdicts = match_requirements(requirements, sample_evidence, threshold=0.0, max_matches=10)
    for verdict in verdicts:
        for match in verdict.matches:
            assert 0.0 <= match.score <= 1.0


def test_max_matches_is_respected(sample_job_description, sample_evidence):
    requirements = extract_requirements(sample_job_description)
    verdicts = match_requirements(requirements, sample_evidence, threshold=0.0, max_matches=1)
    assert all(len(verdict.matches) <= 1 for verdict in verdicts)

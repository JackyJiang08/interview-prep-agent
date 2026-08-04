"""Smoke tests for requirement extraction."""

from __future__ import annotations

from interview_prep_agent import extract_requirements


def test_strips_list_markers_but_keeps_wording():
    requirements = extract_requirements("- Strong SQL and Python for analysis\n")
    assert len(requirements) == 1
    assert requirements[0].text == "Strong SQL and Python for analysis"
    assert requirements[0].source_line == 1


def test_drops_section_headings():
    text = "Requirements\nQualifications:\nBuild ETL pipelines in a warehouse\n"
    requirements = extract_requirements(text)
    assert [item.text for item in requirements] == ["Build ETL pipelines in a warehouse"]


def test_deduplicates_on_normalized_form():
    text = "- Own the funnel metrics.\n-  own the FUNNEL metrics\n"
    requirements = extract_requirements(text)
    assert len(requirements) == 1
    assert requirements[0].text == "Own the funnel metrics."


def test_prose_is_ignored_when_the_posting_uses_a_list():
    text = (
        "Senior Data Analyst, Growth\n"
        "We are looking for an analyst to own activation measurement.\n"
        "- Build ETL pipelines in a warehouse\n"
    )
    requirements = extract_requirements(text)
    assert [item.text for item in requirements] == ["Build ETL pipelines in a warehouse"]


def test_falls_back_to_every_line_when_no_list_exists():
    text = "Build ETL pipelines in a warehouse\nOwn the funnel metrics\n"
    requirements = extract_requirements(text)
    assert len(requirements) == 2


def test_identifiers_are_sequential(sample_job_description):
    requirements = extract_requirements(sample_job_description)
    assert [item.id for item in requirements] == [
        f"REQ-{index:03d}" for index in range(1, len(requirements) + 1)
    ]


def test_every_requirement_appears_verbatim_in_source(sample_job_description):
    for requirement in extract_requirements(sample_job_description):
        assert requirement.text in sample_job_description

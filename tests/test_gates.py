"""Unit tests for the deterministic requirement gates."""

from __future__ import annotations

import pytest

from interview_prep_agent import Requirement, collect_requirement_errors
from interview_prep_agent.workflow.gates import QualityGateError, check_requirements, fold

POSTING = """Requirements
- Strong SQL and Python for analysis on large datasets
- Experience designing and interpreting A/B tests
- Build and maintain ETL pipelines in a cloud data warehouse
"""


def requirement(index: int, text: str, quote: str | None = None) -> Requirement:
    return Requirement(
        id=f"REQ-{index:03d}",
        text=text,
        normalized=text.casefold(),
        source_quote=text if quote is None else quote,
    )


def test_grounded_set_passes():
    requirements = [
        requirement(1, "Strong SQL and Python for analysis on large datasets"),
        requirement(2, "Experience designing and interpreting A/B tests"),
    ]
    assert collect_requirement_errors(POSTING, requirements) == []


def test_quote_absent_from_the_posting_is_rejected():
    requirements = [
        requirement(1, "Ten years of robotics leadership", quote="Ten years of robotics")
    ]
    errors = collect_requirement_errors(POSTING, requirements)
    assert errors == ["grounding: REQ-001 source quote does not appear in the job description"]


def test_missing_quote_is_rejected():
    item = Requirement(id="REQ-001", text="Own the funnel", normalized="own the funnel")
    errors = collect_requirement_errors(POSTING, [item])
    assert errors == ["grounding: REQ-001 carries no source quote"]


def test_grounding_tolerates_wrapping_and_case():
    quote = "strong SQL   and Python\nfor analysis on large datasets"
    errors = collect_requirement_errors(POSTING, [requirement(1, "x" * 10, quote=quote)])
    assert errors == []


def test_non_sequential_identifiers_are_rejected():
    requirements = [
        requirement(1, "Strong SQL and Python for analysis on large datasets"),
        requirement(3, "Experience designing and interpreting A/B tests"),
    ]
    errors = collect_requirement_errors(POSTING, requirements)
    assert any("must run sequentially" in error for error in errors)


def test_duplicate_identifiers_are_rejected():
    requirements = [
        requirement(1, "Strong SQL and Python for analysis on large datasets"),
        requirement(1, "Experience designing and interpreting A/B tests"),
    ]
    errors = collect_requirement_errors(POSTING, requirements)
    assert "identity: requirement identifiers must be unique" in errors


def test_duplicate_statements_are_rejected():
    text = "Strong SQL and Python for analysis on large datasets"
    requirements = [requirement(1, text), requirement(2, text)]
    errors = collect_requirement_errors(POSTING, requirements)
    assert "identity: requirement statements must be unique" in errors


def test_count_below_the_lower_bound_is_rejected():
    errors = collect_requirement_errors(POSTING, [], min_requirements=1)
    assert errors[0].startswith("coverage: expected between 1 and 50 requirements")


def test_count_above_the_upper_bound_is_rejected():
    requirements = [
        requirement(index, f"Strong SQL and Python {'x' * index}") for index in range(1, 4)
    ]
    errors = collect_requirement_errors(
        POSTING, requirements, min_requirements=1, max_requirements=2
    )
    assert any("expected between 1 and 2 requirements, received 3" in e for e in errors)


def test_every_failure_is_reported_not_just_the_first():
    requirements = [
        requirement(2, "Unrelated demand about robotics", quote="robotics"),
        requirement(3, "Another unrelated demand", quote="also absent"),
    ]
    errors = collect_requirement_errors(POSTING, requirements)
    assert len(errors) == 3


def test_check_form_raises_with_every_error_joined():
    item = requirement(1, "Ten years of robotics", quote="not in the posting")
    with pytest.raises(QualityGateError, match="grounding"):
        check_requirements(POSTING, [item])


def test_fold_collapses_whitespace_and_case():
    assert fold("  Strong   SQL\nand Python ") == "strong sql and python"

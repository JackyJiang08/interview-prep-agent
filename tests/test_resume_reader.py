"""The resume reader against resumes shaped like real ones.

Three fixtures, none of them tidy: a paragraph-style resume, the text a PDF
extractor produces, and a mixed one. Each must yield a sensible corpus —
bounded in size, every summary a readable claim, identifiers stable — and
the shape rules must hold in the stated order of preference.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_prep_agent.corpus import CorpusError, looks_like_heading, parse_evidence_markdown

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "low", "high"),
    [("paragraph_style.md", 5, 9), ("pdf_extracted.txt", 4, 9), ("mixed.md", 8, 12)],
)
def test_each_real_shape_yields_a_sensible_corpus(name, low, high):
    items = parse_evidence_markdown(_read(name))
    assert low <= len(items) <= high, [item.summary for item in items]
    assert [item.id for item in items] == [f"EV-{n:03d}" for n in range(1, len(items) + 1)]
    for item in items:
        assert len(item.summary) >= 6 and item.summary == item.summary.strip()
        assert item.source
    # Reading the same text twice yields the same corpus.
    assert parse_evidence_markdown(_read(name)) == items


def test_paragraph_blocks_under_headings_become_one_item_each():
    items = parse_evidence_markdown(_read("paragraph_style.md"))
    summaries = [item.summary for item in items]
    sources = [item.source for item in items]
    assert any(s.startswith("Owned funnel analysis") and "under an hour" in s for s in summaries)
    assert any(s.startswith("Designed and read out four A/B tests") for s in summaries)
    assert "Summary" in sources and "Skills" in sources
    # A dated role line is the subsection its paragraphs trace to, not an item.
    assert "Experience / Data Analyst, Example Co. 2022 to present" in sources
    assert not any(s.startswith("Data Analyst, Example Co.") for s in summaries)
    # The contact line is not a claim about experience.
    assert not any("example.org" in s for s in summaries)


def test_pdf_extracted_text_drops_furniture_and_groups_wrapped_sentences():
    items = parse_evidence_markdown(_read("pdf_extracted.txt"))
    summaries = [item.summary for item in items]
    joined = " ".join(summaries)
    assert "Page 1 of 2" not in joined and "Page 2 of 2" not in joined
    # Wrapped lines rejoin into sentences rather than one item per line.
    assert any(
        "writing SQL against a warehouse of roughly forty million events" in s for s in summaries
    )
    assert not any(
        s == "warehouse of roughly forty million events and modelling results in Python."
        for s in summaries
    )
    # Plain capitalised lines read as headings and populate the source, and
    # the dated role lines beneath them become subsections.
    sections = {item.source.split(" / ")[0] for item in items}
    assert sections >= {"EXPERIENCE", "EDUCATION", "SKILLS"}
    assert any(
        item.source == "EXPERIENCE / Analytics Intern, Sample Labs Summer 2021" for item in items
    )


def test_mixed_resumes_prefer_bullets_then_numbers_then_paragraphs():
    items = parse_evidence_markdown(_read("mixed.md"))
    by_summary = {item.summary: item for item in items}
    # Bullets and numbered lines are one item each, exactly as written.
    assert (
        "Reduced a weekly reporting cycle from two days to under an hour with a scheduled pipeline"
        in by_summary
    )
    assert "Built the first version of the team's churn dashboard" in by_summary
    assert by_summary["Airflow, dbt"].source == "Skills"
    # The paragraph under the subsection is its own item, with the full path.
    paragraph = next(
        item for item in items if item.summary.startswith("Owned the subscription funnel")
    )
    assert paragraph.source == "Experience / Data Analyst, Example Co."
    # The preamble sentence is evidence too; the name alone is not.
    assert any(item.summary.startswith("Data analyst who likes") for item in items)
    assert not any(item.summary == "Jordan Example" for item in items)


def test_bare_paragraphs_with_no_headings_split_on_blank_lines():
    text = (
        "Led a two-person team migrating reports to a new warehouse. Finished a month early.\n"
        "\n"
        "Wrote the runbook the team still uses.\n"
    )
    items = parse_evidence_markdown(text)
    assert [item.summary for item in items] == [
        "Led a two-person team migrating reports to a new warehouse. Finished a month early.",
        "Wrote the runbook the team still uses.",
    ]
    assert all(item.source == "Resume" for item in items)


def test_a_long_paragraph_is_split_at_sentence_boundaries():
    sentence = "Delivered a measurable improvement to a named metric in a named quarter. "
    items = parse_evidence_markdown(sentence * 12)
    assert len(items) >= 2
    for item in items:
        assert len(item.summary) <= 480
        assert item.summary.endswith(".")


def test_only_genuinely_empty_content_errors():
    with pytest.raises(CorpusError, match="no readable content"):
        parse_evidence_markdown("")
    with pytest.raises(CorpusError, match="no readable content"):
        parse_evidence_markdown("## Experience\n\nPage 1 of 1\n\n---\n")


def test_the_heading_heuristic():
    assert looks_like_heading("Experience")
    assert looks_like_heading("PROFESSIONAL EXPERIENCE:")
    assert looks_like_heading("SKILLS")
    assert not looks_like_heading("AWS")  # too short in capitals to be a section
    assert not looks_like_heading("Reduced a reporting cycle from two days to one hour.")
    assert not looks_like_heading("Data Analyst, Example Co. 2022 to present")

"""The research stage - role intelligence for preparation only.

Deterministic code end to end: it splits provided notes, builds a bounded
query set from the posting and the top requirements, calls the search seam,
dedupes, caps, and mints sequential ``SRC-`` identifiers. No model call
happens here; models consume findings downstream, in the preparation
prompts.

The invariant this stage lives under: research informs preparation only. It
runs after matching, its findings are never matchable, and extraction and
matching never see it - the same rule round context follows.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models import Requirement, ResearchFinding, ResearchSourceKind
from ..search import SearchError, SearchProvider

PROVIDED_MARKER = "provided by the user"

# Titles longer than this are cut at a word boundary; the full text stays in
# the summary.
MAX_TITLE_CHARS = 80


def parse_provided_research(text: str) -> list[tuple[str, str]]:
    """Split pasted notes into (title, summary) pairs, one per block.

    Blocks are separated by blank lines. The first line of a block is its
    title - truncated at a word boundary when long - and the whole block is
    the summary, so nothing the user pasted is lost.
    """
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    pairs: list[tuple[str, str]] = []
    for block in blocks:
        first_line = block.splitlines()[0].strip().lstrip("-* ").strip()
        title = first_line
        if len(title) > MAX_TITLE_CHARS:
            cut = title.rfind(" ", 0, MAX_TITLE_CHARS)
            title = title[: cut if cut > 0 else MAX_TITLE_CHARS]
        summary = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if title:
            pairs.append((title, summary))
    return pairs


def build_queries(
    job_description: str,
    requirements: Sequence[Requirement],
    max_queries: int,
) -> list[str]:
    """Build the bounded, deterministic query set.

    The posting's first non-empty line names the role (and often the
    company); the remaining queries come from the highest-importance
    requirements in queue order.
    """
    if max_queries <= 0:
        return []
    role_line = next(
        (line.strip() for line in job_description.splitlines() if line.strip()),
        "",
    )
    queries: list[str] = []
    if role_line:
        queries.append(f"{role_line} reported interview questions")
        queries.append(f"{role_line} role expectations")
    ranked = sorted(requirements, key=lambda item: (-(item.importance or 0), item.id))
    for requirement in ranked:
        if len(queries) >= max_queries:
            break
        queries.append(f"{role_line} interview {requirement.text}".strip())
    return queries[:max_queries]


def gather_research(
    job_description: str,
    requirements: Sequence[Requirement],
    provided_text: str,
    search: SearchProvider | None,
    max_queries: int,
    max_findings: int,
) -> list[ResearchFinding]:
    """Assemble the run's findings: provided notes first, then search.

    Deduplicates by URL and by case-folded title, caps the total, and mints
    sequential identifiers. With no provided text and no search provider the
    result is an empty list and the run is unchanged.
    """
    findings: list[ResearchFinding] = []
    seen: set[str] = set()

    def mint(
        kind: ResearchSourceKind, title: str, summary: str, url: str | None, query: str
    ) -> None:
        if len(findings) >= max_findings:
            return
        key = (url or title).casefold()
        if key in seen:
            return
        seen.add(key)
        findings.append(
            ResearchFinding(
                finding_id=f"SRC-{len(findings) + 1:03d}",
                source_kind=kind,
                title=title,
                summary=summary,
                url=url,
                retrieved_for=query,
            )
        )

    for title, summary in parse_provided_research(provided_text or ""):
        mint(ResearchSourceKind.PROVIDED, title, summary, None, PROVIDED_MARKER)

    if search is not None and max_findings > 0:
        for query in build_queries(job_description, requirements, max_queries):
            try:
                results = search.search(query, max_results=3)
            except SearchError:
                # A failed query degrades to fewer findings, never to a
                # failed run: research is auxiliary by design.
                continue
            for row in results:
                mint(
                    ResearchSourceKind.SEARCH,
                    row["title"],
                    row["snippet"] or row["title"],
                    row["url"],
                    query,
                )

    return findings

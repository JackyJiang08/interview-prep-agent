"""Reading job-description text and evidence corpora from disk.

Evidence arrives in either of two forms and lands in the same model: a YAML
or JSON corpus written by hand, or a markdown or plain-text resume whose
bullets and paragraphs are normalized into evidence items with sequential
stable identifiers. The
identifier is the unit of traceability, so it is assigned here, once, at the
boundary — nothing downstream mints one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Clarification, EvidenceItem


class CorpusError(ValueError):
    """Raised when an input file cannot be read as a valid corpus."""


def load_job_description(path: str | Path) -> str:
    """Read a job description as plain text."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise CorpusError(f"job description at {path} is empty")
    return text


def load_evidence(path: str | Path) -> list[EvidenceItem]:
    """Read evidence from a corpus file or a markdown resume.

    Dispatches on the suffix: ``.md`` and ``.markdown`` are read as a resume
    whose bullets become evidence items; anything else is read as a YAML or
    JSON corpus. Both routes produce the same model with unique identifiers,
    because every match cites one.
    """
    source = Path(path)
    raw_text = source.read_text(encoding="utf-8")

    if source.suffix.lower() in (".md", ".markdown"):
        return parse_evidence_markdown(raw_text)
    return parse_evidence_corpus(raw_text, str(path), source.suffix.lower())


def parse_evidence_corpus(raw_text: str, label: str, suffix: str = ".yaml") -> list[EvidenceItem]:
    """Parse a YAML or JSON corpus into evidence items.

    Each entry needs ``id`` and ``summary``; ``skills``, ``impact`` and
    ``source`` are optional.
    """
    if suffix == ".json":
        payload = json.loads(raw_text)
    else:
        payload = yaml.safe_load(raw_text)

    if isinstance(payload, dict) and "evidence" in payload:
        payload = payload["evidence"]

    if not isinstance(payload, list):
        raise CorpusError(f"evidence at {label} must be a list of items")

    try:
        items = [EvidenceItem(**entry) for entry in payload]
    except (TypeError, ValidationError) as error:
        raise CorpusError(f"invalid evidence in {label}: {error}") from error

    identifiers = [item.id for item in items]
    if len(set(identifiers)) != len(identifiers):
        raise CorpusError("evidence identifiers must be unique")

    return items


def parse_evidence_markdown(markdown: str) -> list[EvidenceItem]:
    """Normalize a markdown or plain-text resume into evidence items.

    Real resumes come in every shape, and the reader takes them in order of
    preference: bullet lines and numbered lines become one item each, with
    wrapped continuation lines joined; paragraph blocks under headings become
    one item per block, with long blocks split at sentence boundaries; and
    paragraphs with no headings at all are split on blank lines. Sentences
    are grouped, never one item per line. Section headings — markdown ones,
    or plain lines that read as headings — populate ``source``, so a citation
    traces back to its place in the resume. Page furniture that PDF
    extraction leaves behind is dropped.

    Identifiers run sequentially from EV-001 in document order.

    Raises:
        CorpusError: If nothing readable remains once furniture is dropped.
    """
    items: list[EvidenceItem] = []

    def mint(summary: str, source: str) -> None:
        items.append(EvidenceItem(id=f"EV-{len(items) + 1:03d}", summary=summary, source=source))

    for kind, text, source in _resume_blocks(markdown):
        if kind == "bullet":
            if text:
                mint(text, source)
            continue
        if _looks_like_contact(text) or len(text.split()) < MIN_PARAGRAPH_WORDS:
            continue
        for chunk in _group_sentences(text):
            mint(chunk, source)

    if not items:
        raise CorpusError(
            "the resume contains no readable content to turn into evidence; "
            "add lines describing what you did"
        )
    return items


# The reader's shape rules. Bullets and numbering open an item; a plain line
# that reads as a heading opens a section; anything else is paragraph text.
_BULLET_LINE = re.compile(r"^\s*(?:[-*+•·▪○●◦‣]|\d{1,3}[.)]|\(\d{1,3}\))\s+(?P<rest>\S.*)$")
_MARKDOWN_HEADING = re.compile(r"^\s*(?P<marks>#{1,6})\s+(?P<title>\S.*?)\s*#*\s*$")
_BOLD_LINE = re.compile(r"^\s*\*\*(?P<title>[^*]+)\*\*\s*:?\s*$")
_PAGE_ARTIFACT = re.compile(r"^\s*(page\s*)?\d+\s*((of|/)\s*\d+)?\s*$", re.IGNORECASE)
_RULE_LINE = re.compile(r"^\s*[-_=*·.]{3,}\s*$")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")
_CONTACT = re.compile(r"@|https?://|linkedin\.com|github\.com|\+?\d[\d\s().-]{7,}\d")

MIN_PARAGRAPH_WORDS = 5
MAX_ITEM_CHARS = 480
MAX_TITLE_WORDS = 10

# A job or degree title line: short, undated prose does not qualify, a
# dated line does — "Data Analyst, Example Co. 2022 to present".
_DATED = re.compile(r"\b(19|20)\d{2}\b|\bpresent\b|\bcurrent\b", re.IGNORECASE)
_SENTENCE_INSIDE = re.compile(r"[.!?]\s+[A-Z]")

HEADING_WORDS = {
    "summary",
    "profile",
    "objective",
    "about",
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "employment history",
    "education",
    "skills",
    "technical skills",
    "core skills",
    "projects",
    "selected projects",
    "publications",
    "certifications",
    "awards",
    "languages",
    "interests",
    "volunteering",
    "leadership",
}


def looks_like_heading(line: str) -> bool:
    """True for a plain line that reads as a resume section heading.

    Either a known section word, or a short line in capitals. Shared with
    the PDF path, which emits the same shape this reader consumes.
    """
    stripped = line.strip().rstrip(":")
    words = stripped.split()
    if not words or len(words) > 6 or stripped.endswith((".", ",", ";")):
        return False
    if " ".join(words).lower() in HEADING_WORDS:
        return True
    letters = [char for char in stripped if char.isalpha()]
    return len(letters) >= 4 and all(char.isupper() for char in letters)


def _resume_blocks(markdown: str) -> list[tuple[str, str, str]]:
    """Cut the resume into (kind, text, source) blocks in document order."""
    blocks: list[tuple[str, str, str]] = []
    section, subsection = "Resume", ""
    kind: str | None = None
    parts: list[str] = []
    part_source = section

    def close() -> None:
        nonlocal kind, parts
        if kind is not None and parts:
            blocks.append((kind, " ".join(part.strip() for part in parts).strip(), part_source))
        kind, parts = None, []

    def source() -> str:
        return " / ".join(part for part in (section, subsection) if part)

    for line in markdown.replace("\f", "\n\n").splitlines():
        stripped = line.strip()
        if not stripped or _RULE_LINE.match(stripped) or _PAGE_ARTIFACT.match(stripped):
            close()
            continue

        heading = _MARKDOWN_HEADING.match(line)
        if heading is not None:
            close()
            if len(heading.group("marks")) >= 3:
                subsection = heading.group("title")
            else:
                section, subsection = heading.group("title"), ""
            continue
        bold = _BOLD_LINE.match(line)
        plain_title = bold.group("title").strip() if bold is not None else stripped
        if looks_like_heading(plain_title):
            close()
            section, subsection = plain_title, ""
            continue

        bullet = _BULLET_LINE.match(line)
        if bullet is not None:
            close()
            kind, parts, part_source = "bullet", [bullet.group("rest")], source()
            continue
        if kind == "bullet" and (line[0].isspace() or stripped[0].islower()):
            parts.append(stripped)  # a wrapped continuation of the open bullet
            continue
        if _looks_like_title(stripped) and (
            kind != "paragraph" or _can_interrupt(parts[-1], stripped)
        ):
            close()
            subsection = stripped.replace("**", "").strip()
            continue
        if kind == "paragraph":
            parts.append(stripped)
            continue
        close()
        kind, parts, part_source = "paragraph", [stripped], source()

    close()
    return blocks


def _group_sentences(text: str) -> list[str]:
    """One item per block, unless the block is long enough to split.

    A long paragraph is cut at sentence boundaries into runs that stay
    under the item ceiling, so each item remains a readable claim.
    """
    if len(text) <= MAX_ITEM_CHARS:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_BREAK.split(text):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > MAX_ITEM_CHARS:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _looks_like_contact(text: str) -> bool:
    """A short line carrying an address, link or phone number, not a claim."""
    return len(text.split()) < 12 and _CONTACT.search(text) is not None


def _can_interrupt(previous: str, line: str) -> bool:
    """Whether a title line may cut an open paragraph: only when the line
    opens with a capital and the previous line was a finished sentence or a
    fragment, never mid-sentence."""
    return line[0].isupper() and (
        previous.rstrip().endswith((".", "!", "?", ":", ")")) or len(previous.split()) <= 4
    )


def _looks_like_title(line: str) -> bool:
    """A dated role or degree line at the start of a block: context, not a
    claim, and the subsection every item under it is traced to."""
    return (
        len(line.split()) <= MAX_TITLE_WORDS
        and not line.endswith(".")
        and _SENTENCE_INSIDE.search(line) is None
        and _DATED.search(line) is not None
    )


def clarification_to_evidence(clarification: Clarification, index: int) -> EvidenceItem:
    """Normalize one human answer into a first-class evidence item.

    Identifiers run in their own ``CL-`` series so a citation is legible about
    where the evidence came from, and the item carries the requirement it
    addresses and the question that was asked. Regeneration passes the
    enlarged corpus through the unchanged workflow, so a match citing a
    clarification cites an identifier that resolves like any other.

    Args:
        clarification: The answered question.
        index: One-based position in the clarification series.
    """
    return EvidenceItem(
        id=f"CL-{index:03d}",
        # The admitted claim, when present, is the summary: nothing stronger
        # than what the admission gate approved can be cited. The raw answer
        # stands in only for clarifications that never passed through a gate.
        summary=clarification.accepted_claim or clarification.answer,
        source="clarification",
        addresses_requirement_id=clarification.requirement_id,
        question=clarification.question,
    )

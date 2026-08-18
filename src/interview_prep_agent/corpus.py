"""Reading job-description text and evidence corpora from disk.

Evidence arrives in either of two forms and lands in the same model: a YAML
or JSON corpus written by hand, or a markdown resume whose bullets are
normalized into evidence items with sequential stable identifiers. The
identifier is the unit of traceability, so it is assigned here, once, at the
boundary — nothing downstream mints one.
"""

from __future__ import annotations

import json
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
    """Normalize a markdown resume's bullets into evidence items.

    Each ``- `` bullet becomes one item, its continuation lines joined into
    the summary. Identifiers run sequentially from EV-001 in document order,
    and ``source`` records the section and subsection headings the bullet sat
    under, so a citation can be traced back to its place in the resume.

    Raises:
        CorpusError: If the resume contains no bullets to normalize.
    """
    items: list[EvidenceItem] = []
    section = "Resume"
    subsection = ""
    bullet_lines: list[str] = []
    bullet_source = section

    def flush() -> None:
        if not bullet_lines:
            return
        items.append(
            EvidenceItem(
                id=f"EV-{len(items) + 1:03d}",
                summary=" ".join(bullet_lines),
                source=bullet_source,
            )
        )
        bullet_lines.clear()

    for line in [*markdown.splitlines(), ""]:
        stripped = line.strip()
        if line.startswith("## "):
            flush()
            section = stripped.removeprefix("## ")
            subsection = ""
        elif line.startswith("### "):
            flush()
            subsection = stripped.removeprefix("### ")
        elif line.startswith("- "):
            flush()
            bullet_source = " / ".join(part for part in (section, subsection) if part)
            bullet_lines.append(line.removeprefix("- ").strip())
        elif bullet_lines and (line.startswith("  ") or stripped):
            # A wrapped continuation of the open bullet.
            bullet_lines.append(stripped)
        else:
            flush()

    if not items:
        raise CorpusError("the resume contains no bullet lines to normalize into evidence")
    return items


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

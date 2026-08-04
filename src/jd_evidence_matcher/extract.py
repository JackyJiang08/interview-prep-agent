"""Stage 1 - turn raw job-description text into atomic requirements.

This stage is deliberately deterministic: the same input always yields the same
requirement list, so a downstream disagreement can never be blamed on sampling.
It removes list markers and section headings, normalizes for comparison, and
drops duplicates while preserving the original wording of the first occurrence.

Postings state their requirements as a list far more often than not, so a line
carrying a list marker is treated as the signal. When a posting has no list at
all, the stage falls back to reading every non-heading line. See
``docs/METHODOLOGY.md`` for what that fallback costs.
"""

from __future__ import annotations

import re
from typing import List

from .models import Requirement

# Leading list markers: bullets, dashes, and "1." / "(2)" style numbering.
_LIST_MARKER = re.compile(r"^\s*(?:[-*•·●▪–—]+|\(?\d{1,2}[.)])\s+")

# Headings that structure a posting but state no requirement of their own.
_HEADING = re.compile(
    r"^\s*(?:"
    r"about\s+(?:us|the\s+(?:role|team|company|job))"
    r"|what\s+you(?:'ll|\s+will)?\s+do"
    r"|(?:minimum|preferred|basic)\s+qualifications"
    r"|qualifications?"
    r"|requirements?"
    r"|responsibilities"
    r"|nice\s+to\s+have"
    r"|who\s+you\s+are"
    r"|benefits"
    r"|compensation"
    r"|how\s+to\s+apply"
    r")\s*:?\s*$",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCT = re.compile(r"[.;,:]+$")

# Below this many characters a line carries no matchable content.
_MIN_LENGTH = 8


def normalize(text: str) -> str:
    """Fold a requirement to a comparable form used only for deduplication."""
    folded = _WHITESPACE.sub(" ", text).strip().lower()
    return _TRAILING_PUNCT.sub("", folded)


def extract_requirements(raw_text: str) -> List[Requirement]:
    """Extract atomic requirements from job-description text.

    Args:
        raw_text: The posting as plain text.

    Returns:
        Requirements in source order, deduplicated on their normalized form.
        Empty when the posting contains no candidate lines.
    """
    lines = raw_text.splitlines()
    listed = any(_LIST_MARKER.match(line) for line in lines)

    found: List[Requirement] = []
    seen = set()

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or _HEADING.match(stripped):
            continue

        # A titled or prose line is not a requirement when the posting lists
        # its requirements explicitly.
        if listed and not _LIST_MARKER.match(line):
            continue

        text = _LIST_MARKER.sub("", stripped).strip()
        if len(text) < _MIN_LENGTH:
            continue

        key = normalize(text)
        if not key or key in seen:
            continue
        seen.add(key)

        found.append(
            Requirement(
                id="REQ-{:03d}".format(len(found) + 1),
                text=text,
                normalized=key,
                source_line=line_number,
            )
        )

    return found

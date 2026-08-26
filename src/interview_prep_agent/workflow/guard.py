"""A deterministic guard on extracted requirements.

Belt and braces after extraction, model-backed or not: a posting's section
headings, its salary line and its equal-opportunity statement are not
requirements, and a model asked for requirements will sometimes return them
anyway. This drops the obvious shapes and anything shorter than a settings
floor. Nothing is dropped silently — every drop is returned with its reason
and recorded in the trace and the artifacts, so a reader can disagree with a
specific drop rather than with the pipeline.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..models import Requirement

# Words a posting uses as section labels. A short line made only of these,
# or a short line ending in a colon, is a heading, not a demand.
HEADING_WORDS = {
    "job",
    "description",
    "title",
    "role",
    "location",
    "about",
    "us",
    "the",
    "team",
    "company",
    "overview",
    "summary",
    "responsibilities",
    "duties",
    "requirements",
    "qualifications",
    "required",
    "preferred",
    "nice",
    "to",
    "have",
    "haves",
    "benefits",
    "perks",
    "salary",
    "compensation",
    "pay",
    "apply",
    "how",
    "what",
    "you",
    "will",
    "do",
    "we",
    "offer",
    "our",
    "your",
    "skills",
    "experience",
    "education",
    "position",
    "department",
    "reports",
    "employment",
    "type",
    "schedule",
    "remote",
    "hybrid",
    "onsite",
    "on-site",
    "and",
    "of",
    "a",
    "an",
    "&",
    "/",
}

_DISCLAIMER = re.compile(
    r"equal[- ]opportunity|\bEEO\b|without regard to|discriminat|protected (class|status|"
    r"characteristic)|reasonable accommodation|background check|drug[- ]screen|"
    r"salary range|pay range|base (pay|salary)|compensation (range|package)|"
    r"\$\s?\d{2,3},\d{3}|\bper (year|annum|hour)\b|\b401\s?\(?k\)?\b|"
    r"health,? dental|paid time off|\bPTO\b",
    re.IGNORECASE,
)

MAX_HEADING_WORDS = 4


def guard_requirements(
    requirements: Sequence[Requirement], min_chars: int
) -> tuple[list[Requirement], list[dict[str, Any]]]:
    """Split requirements into those kept and those dropped, with reasons.

    The kept items are renumbered to run from REQ-001 in source order, which
    is what the requirement gate demands; each drop record carries the
    identifier the item had before the guard, so the trace still says which
    extracted line was refused and why.
    """
    kept: list[Requirement] = []
    dropped: list[dict[str, Any]] = []
    for requirement in requirements:
        reason = drop_reason(requirement.text, min_chars)
        if reason is None:
            kept.append(requirement.model_copy(update={"id": f"REQ-{len(kept) + 1:03d}"}))
        else:
            dropped.append({"id": requirement.id, "text": requirement.text, "reason": reason})
    return kept, dropped


def drop_reason(text: str, min_chars: int) -> str | None:
    """Why a requirement text is not one, or None when it passes."""
    stripped = text.strip()
    # Shape first, length last: a short heading is refused as a heading,
    # which tells a reader more than its length would.
    if _is_heading(stripped):
        return "reads as a section heading"
    if _DISCLAIMER.search(stripped):
        return "reads as a salary, benefits or equal-opportunity statement"
    if len(stripped) < min_chars:
        return f"shorter than {min_chars} characters"
    return None


def _is_heading(text: str) -> bool:
    words = text.rstrip(":").split()
    if not words or len(words) > MAX_HEADING_WORDS:
        return False
    if text.endswith(":"):
        return True
    lowered = [word.strip("'\"()").lower() for word in words]
    return all(word in HEADING_WORDS for word in lowered)

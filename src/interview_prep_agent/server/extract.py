"""PDF resume intake: extract the text and shape it for the corpus reader.

The corpus reader accepts a markdown resume — ``## `` headings, ``- ``
bullets, continuation lines under a bullet, blank lines between blocks.
A PDF's text layer arrives as bare lines with page furniture mixed in, so
this module extracts it and normalizes toward that shape: headings kept
where they can be told apart, bullets preserved, furniture dropped. It is
a heuristic pass; what it produced is shown to the visitor to correct
before anything runs, and no session depends on it succeeding.
"""

from __future__ import annotations

import re
from collections import Counter
from io import BytesIO

BULLET_MARKERS = "•·▪○●◦‣–—*-"

# Section titles a resume states in words. Matched whole, case-insensitively.
HEADING_WORDS = {
    "summary",
    "profile",
    "objective",
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "education",
    "skills",
    "technical skills",
    "projects",
    "publications",
    "certifications",
    "awards",
    "languages",
    "interests",
    "volunteering",
}

_PAGE_NUMBER = re.compile(r"^\s*(page\s*)?\d+\s*((of|/)\s*\d+)?\s*$", re.IGNORECASE)
_BULLET = re.compile(rf"^\s*[{re.escape(BULLET_MARKERS)}]\s+(?P<rest>\S.*)$")


class ExtractionRefused(Exception):
    """A structured refusal, in the same shape the session layer uses."""

    def __init__(self, status_code: int, category: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.category = category
        self.message = message


def extract_resume(pdf_bytes: bytes) -> tuple[str, int]:
    """Return the normalized text and page count of a PDF resume.

    Raises:
        ExtractionRefused: If the bytes are not a readable PDF, or the PDF
            carries no text layer — a scan — in which case the visitor is
            told to paste the text instead.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as error:  # noqa: BLE001 - the library's errors are not a taxonomy
        raise ExtractionRefused(
            422,
            "unreadable_pdf",
            "this file could not be read as a PDF; paste the resume text instead",
        ) from error

    if not any(page.strip() for page in pages):
        raise ExtractionRefused(
            422,
            "no_text_layer",
            "this PDF has no text layer - it is likely a scan; paste the resume text instead",
        )
    return normalize_resume_text(pages), len(pages)


def normalize_resume_text(pages: list[str]) -> str:
    """Shape extracted page texts toward the markdown resume the reader accepts."""
    furniture = _repeated_lines(pages)
    output: list[str] = []
    last_kind = "blank"

    for page in pages:
        for raw in page.splitlines():
            line = raw.strip()
            if not line:
                if last_kind != "blank":
                    output.append("")
                    last_kind = "blank"
                continue
            if _PAGE_NUMBER.match(line) or line in furniture:
                continue

            bullet = _BULLET.match(line)
            if bullet is not None:
                if last_kind == "text":
                    output.append("")
                output.append(f"- {bullet.group('rest').strip()}")
                last_kind = "bullet"
            elif _is_heading(line):
                if last_kind != "blank":
                    output.append("")
                output.append(f"## {line.rstrip(':')}")
                output.append("")
                last_kind = "blank"
            elif last_kind == "bullet" and line[0].islower():
                # A wrapped continuation of the open bullet.
                output.append(f"  {line}")
            else:
                if last_kind == "bullet":
                    output.append("")
                output.append(line)
                last_kind = "text"

    return "\n".join(output).strip() + "\n"


def _repeated_lines(pages: list[str]) -> set[str]:
    """Lines that recur on every page of a multi-page document: running
    headers and footers, which carry no content."""
    if len(pages) < 2:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        for line in {raw.strip() for raw in page.splitlines() if raw.strip()}:
            counts[line] += 1
    return {line for line, count in counts.items() if count == len(pages)}


def _is_heading(line: str) -> bool:
    words = line.rstrip(":").split()
    if not words or len(words) > 6 or line.endswith((".", ",", ";")):
        return False
    lowered = " ".join(words).lower()
    if lowered in HEADING_WORDS:
        return True
    letters = [char for char in line if char.isalpha()]
    return len(letters) >= 3 and all(char.isupper() for char in letters)

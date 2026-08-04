"""Validated data contracts shared by every stage of the pipeline.

Each stage consumes and emits one of these models. Because every stage boundary
is validated, a bad result can be attributed to a specific stage instead of to
the system as a whole.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, NonNegativeFloat


class Requirement(BaseModel):
    """A single atomic requirement lifted from a job description.

    ``text`` holds the wording exactly as it appeared in the source (after only
    list-marker removal). Downstream stages may read ``normalized`` for
    comparison, but anything shown to a user must quote ``text``.
    """

    id: str = Field(pattern=r"^REQ-\d{3,}$")
    text: str = Field(min_length=1)
    normalized: str = Field(min_length=1)
    source_line: int = Field(ge=1)


class EvidenceItem(BaseModel):
    """One attested item from the candidate's evidence corpus."""

    id: str = Field(pattern=r"^EV-\d{3,}$")
    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    impact: Optional[str] = None


class EvidenceMatch(BaseModel):
    """A scored link between one requirement and one evidence item."""

    evidence_id: str
    score: NonNegativeFloat
    overlapping_terms: list[str] = Field(default_factory=list)


class Status(str, Enum):
    """Whether a requirement is supported by the evidence corpus."""

    PROOF = "PROOF"
    GAP = "GAP"


class RequirementMatch(BaseModel):
    """The matcher's verdict for one requirement."""

    requirement_id: str
    status: Status
    matches: list[EvidenceMatch] = Field(default_factory=list)
    method: str


class PlanItem(BaseModel):
    """One entry in the focus plan, gap-first ordered."""

    requirement: Requirement
    status: Status
    matches: list[EvidenceMatch] = Field(default_factory=list)
    note: str


class Coverage(BaseModel):
    """Requirement accounting for the whole run."""

    total: int = Field(ge=0)
    proof: int = Field(ge=0)
    gap: int = Field(ge=0)


class FocusPlan(BaseModel):
    """Final artifact: every requirement, gaps first, each traceable."""

    coverage: Coverage
    items: list[PlanItem] = Field(default_factory=list)
    method: str

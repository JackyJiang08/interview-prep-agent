"""Evidence-grounded requirement matching for job descriptions.

The pipeline turns a posting plus an evidence corpus into a gap-first focus
plan in which every supported requirement cites the evidence that supports it.
"""

from __future__ import annotations

from .config import Settings, load_settings
from .corpus import load_evidence, load_job_description
from .extract import extract_requirements
from .match import match_requirements
from .models import (
    Coverage,
    EvidenceItem,
    EvidenceMatch,
    FocusPlan,
    PlanItem,
    Requirement,
    RequirementMatch,
    Status,
)
from .pipeline import run_pipeline
from .plan import QualityGateError, build_focus_plan

__version__ = "0.1.0"

__all__ = [
    "Coverage",
    "EvidenceItem",
    "EvidenceMatch",
    "FocusPlan",
    "PlanItem",
    "QualityGateError",
    "Requirement",
    "RequirementMatch",
    "Settings",
    "Status",
    "build_focus_plan",
    "extract_requirements",
    "load_evidence",
    "load_job_description",
    "load_settings",
    "match_requirements",
    "run_pipeline",
    "__version__",
]

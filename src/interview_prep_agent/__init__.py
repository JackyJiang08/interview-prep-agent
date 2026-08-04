"""Evidence-grounded requirement matching.

The ``workflow`` subpackage holds the deterministic three-stage pipeline that
turns a posting plus an evidence corpus into a gap-first plan in which every
supported requirement cites the evidence supporting it. Shared contracts,
settings, corpus loading and the command-line interface sit at package root so
that later layers can reuse them without depending on the workflow itself.
"""

from __future__ import annotations

from .config import Settings, load_settings
from .corpus import load_evidence, load_job_description
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
from .workflow import (
    QualityGateError,
    build_focus_plan,
    extract_requirements,
    match_requirements,
    run_pipeline,
)

__version__ = "0.2.0"

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

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
    CoverageLevel,
    EvidenceItem,
    EvidenceMatch,
    FocusArea,
    FocusPlan,
    InterviewStrategy,
    MatchAssessment,
    MatchAssessmentList,
    MockQuestion,
    MockQuestionList,
    PlanItem,
    PrepPackage,
    Requirement,
    RequirementCategory,
    RequirementExtraction,
    RequirementMatch,
    RequirementType,
    RiskItem,
    Status,
    StoryPlan,
    StrategyItem,
)
from .providers import ProviderError, StructuredModel, build_model
from .workflow import (
    QualityGateError,
    build_focus_areas,
    build_focus_plan,
    build_workflow,
    check_matches,
    collect_match_errors,
    collect_requirement_errors,
    extract_requirements,
    extract_requirements_with_model,
    match_requirements,
    run_pipeline,
    run_workflow,
)

__version__ = "0.4.0"

__all__ = [
    "Coverage",
    "CoverageLevel",
    "EvidenceItem",
    "EvidenceMatch",
    "FocusArea",
    "FocusPlan",
    "InterviewStrategy",
    "MatchAssessment",
    "MatchAssessmentList",
    "MockQuestion",
    "MockQuestionList",
    "PrepPackage",
    "PlanItem",
    "QualityGateError",
    "ProviderError",
    "Requirement",
    "RequirementCategory",
    "RequirementExtraction",
    "RequirementMatch",
    "RequirementType",
    "RiskItem",
    "Settings",
    "Status",
    "StoryPlan",
    "StrategyItem",
    "StructuredModel",
    "build_focus_plan",
    "build_model",
    "build_workflow",
    "build_focus_areas",
    "check_matches",
    "collect_match_errors",
    "collect_requirement_errors",
    "extract_requirements",
    "extract_requirements_with_model",
    "load_evidence",
    "load_job_description",
    "load_settings",
    "match_requirements",
    "run_pipeline",
    "run_workflow",
    "__version__",
]

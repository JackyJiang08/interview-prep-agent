"""The deterministic workflow layer.

Three stages run in a fixed order on every invocation: extract requirements
from a posting, score them against an evidence corpus, and assemble a gap-first
plan behind quality gates. Control flow lives in code here, not in a model.

This layer is self-contained. Anything added around it later composes with the
stages rather than replacing them, and the guarantees the gates enforce hold
regardless of what calls in.
"""

from __future__ import annotations

from .extract import extract_requirements, normalize
from .extract_model import extract_requirements_with_model, parse_extraction
from .gates import (
    QualityGateError,
    check_plan,
    check_requirements,
    collect_plan_errors,
    collect_requirement_errors,
)
from .graph import WorkflowState, build_workflow, route_after_validation
from .match import METHOD_NAME, match_requirements, score_requirement, tokenize
from .pipeline import (
    EXTRACTORS,
    LEXICAL,
    MATCHES_ARTIFACT,
    MODEL_BACKED,
    PLAN_ARTIFACT,
    REQUIREMENTS_ARTIFACT,
    run_pipeline,
    run_workflow,
)
from .plan import build_focus_plan

__all__ = [
    "EXTRACTORS",
    "LEXICAL",
    "MATCHES_ARTIFACT",
    "METHOD_NAME",
    "MODEL_BACKED",
    "PLAN_ARTIFACT",
    "QualityGateError",
    "REQUIREMENTS_ARTIFACT",
    "WorkflowState",
    "build_focus_plan",
    "build_workflow",
    "check_plan",
    "check_requirements",
    "collect_plan_errors",
    "collect_requirement_errors",
    "extract_requirements",
    "extract_requirements_with_model",
    "match_requirements",
    "normalize",
    "parse_extraction",
    "route_after_validation",
    "run_pipeline",
    "run_workflow",
    "score_requirement",
    "tokenize",
]

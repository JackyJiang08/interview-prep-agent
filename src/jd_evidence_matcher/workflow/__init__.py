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
from .match import METHOD_NAME, match_requirements, score_requirement, tokenize
from .pipeline import (
    MATCHES_ARTIFACT,
    PLAN_ARTIFACT,
    REQUIREMENTS_ARTIFACT,
    run_pipeline,
)
from .plan import QualityGateError, build_focus_plan

__all__ = [
    "MATCHES_ARTIFACT",
    "METHOD_NAME",
    "PLAN_ARTIFACT",
    "QualityGateError",
    "REQUIREMENTS_ARTIFACT",
    "build_focus_plan",
    "extract_requirements",
    "match_requirements",
    "normalize",
    "run_pipeline",
    "score_requirement",
    "tokenize",
]

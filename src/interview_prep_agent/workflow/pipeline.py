"""Running the workflow.

The graph in :mod:`.graph` is the runtime. This module is the façade over it:
:func:`run_workflow` returns the final state, errors and all, which is what a
caller wiring the workflow into something larger wants. :func:`run_pipeline`
keeps the older contract — a plan, or an exception — because a violated
guarantee should stop a command-line run rather than return something that
looks like a plan.

Per-stage artifacts are written after the run rather than by the nodes
themselves, so that state stays business data and nothing in the graph reaches
for the filesystem.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from ..models import EvidenceItem, FocusArea, FocusPlan, Requirement, RequirementMatch
from ..providers import StructuredModel
from .extract import extract_requirements
from .extract_model import extract_requirements_with_model
from .gates import QualityGateError
from .graph import PrepState, WorkflowState, build_prep_workflow, build_workflow
from .match_model import match_evidence_with_model

REQUIREMENTS_ARTIFACT = "requirements.json"
DROPPED_ARTIFACT = "dropped_requirements.json"
MATCHES_ARTIFACT = "matches.json"
FOCUS_AREAS_ARTIFACT = "focus_areas.json"
PLAN_ARTIFACT = "focus_plan.json"
RESEARCH_ARTIFACT = "research_findings.json"
STRATEGY_ARTIFACT = "strategy.json"
QUESTIONS_ARTIFACT = "questions.json"
PACKAGE_ARTIFACT = "prep_package.json"

LEXICAL = "lexical"
MODEL_BACKED = "llm"
EXTRACTORS = (LEXICAL, MODEL_BACKED)
MATCHERS = (LEXICAL, MODEL_BACKED)


def _resolve_extractor(extractor: str, model: StructuredModel | None):
    if extractor == LEXICAL:
        return extract_requirements
    if extractor == MODEL_BACKED:
        if model is None:
            raise ValueError(
                "the llm extractor needs a provider; pass model=... or use the lexical extractor"
            )
        return lambda text: extract_requirements_with_model(text, model)
    raise ValueError(f"unknown extractor {extractor!r}; choose from {', '.join(EXTRACTORS)}")


def _resolve_matcher(matcher: str, model: StructuredModel | None):
    """Return a matcher callable for the graph, or None for the built-in default."""
    if matcher == LEXICAL:
        return None
    if matcher == MODEL_BACKED:
        if model is None:
            raise ValueError(
                "the llm matcher needs a provider; pass model=... or use the lexical matcher"
            )
        return lambda requirements, evidence: match_evidence_with_model(
            requirements, evidence, model
        )
    raise ValueError(f"unknown matcher {matcher!r}; choose from {', '.join(MATCHERS)}")


def run_workflow(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    settings=None,
    extractor: str = LEXICAL,
    model: StructuredModel | None = None,
    matcher: str = LEXICAL,
) -> WorkflowState:
    """Run the graph and return its final state.

    Requirement validation failures are reported in the returned state rather
    than raised, because routing on them is the graph's job.

    Args:
        job_description: Raw posting text.
        evidence: The candidate's evidence corpus.
        settings: Pipeline settings; packaged defaults are used if omitted.
        extractor: ``"lexical"`` or ``"llm"``.
        model: Provider used when either stage is ``"llm"``; one instance
            serves both.
        matcher: ``"lexical"`` or ``"llm"``.

    Returns:
        Final state, including ``plan`` when valid and ``validation_errors``
        when not.
    """
    from ..config import load_settings

    settings = settings or load_settings()
    workflow = build_workflow(
        extractor=_resolve_extractor(extractor, model),
        matcher=_resolve_matcher(matcher, model),
        match_threshold=settings.match_threshold,
        max_matches=settings.max_matches_per_requirement,
        min_requirements=settings.min_requirements,
        max_requirements=settings.max_requirements,
        min_requirement_chars=settings.min_requirement_chars,
    )
    return workflow.invoke({"job_description": job_description, "evidence": list(evidence)})


def run_pipeline(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    settings=None,
    output_dir: Path | None = None,
    extractor: str = LEXICAL,
    model: StructuredModel | None = None,
    matcher: str = LEXICAL,
) -> FocusPlan:
    """Run the workflow and return the plan.

    Args:
        job_description: Raw posting text.
        evidence: The candidate's evidence corpus.
        settings: Pipeline settings; packaged defaults are used if omitted.
        output_dir: Where to write per-stage artifacts. Nothing is written when
            omitted or when ``write_stage_artifacts`` is off.
        extractor: ``"lexical"`` or ``"llm"``.
        model: Provider used when either stage is ``"llm"``; one instance
            serves both.
        matcher: ``"lexical"`` or ``"llm"``.

    Returns:
        The focus plan, ordered by preparation priority.

    Raises:
        QualityGateError: If extraction produced a requirement set that fails
            the grounding gate, or if matching lost or mis-cited anything.
    """
    from ..config import load_settings

    settings = settings or load_settings()
    state = run_workflow(job_description, evidence, settings, extractor, model, matcher)

    if not state.get("requirements_valid", False):
        raise QualityGateError("; ".join(state.get("validation_errors", [])))

    plan = state["plan"]
    if output_dir is not None and settings.write_stage_artifacts:
        _write_artifacts(
            Path(output_dir),
            state["requirements"],
            state["matches"],
            state["focus_areas"],
            plan,
        )
    return plan


def _write_artifacts(
    output_dir: Path,
    requirements: list[Requirement],
    verdicts: list[RequirementMatch],
    focus_areas: list[FocusArea],
    plan: FocusPlan,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    _dump(
        output_dir / REQUIREMENTS_ARTIFACT,
        [item.model_dump(mode="json", exclude_none=True) for item in requirements],
    )
    _dump(
        output_dir / MATCHES_ARTIFACT,
        [item.model_dump(mode="json") for item in verdicts],
    )
    _dump(
        output_dir / FOCUS_AREAS_ARTIFACT,
        [item.model_dump(mode="json") for item in focus_areas],
    )
    _dump(output_dir / PLAN_ARTIFACT, plan.model_dump(mode="json", exclude_none=True))


def _dump(path: Path, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def run_prep(
    job_description: str,
    evidence_source: str,
    evidence_format: str,
    settings=None,
    output_dir: Path | None = None,
    extractor: str = LEXICAL,
    matcher: str = LEXICAL,
    model: StructuredModel | None = None,
    research_text: str = "",
    search=None,
    company: str = "",
    role_title: str = "",
) -> PrepState:
    """Run the full preparation graph and return its final state.

    Package validation failures are reported in the state rather than raised —
    routing on them is the graph's job — while input, grounding and match
    violations raise, exactly as they do on the shorter path.

    Per-stage artifacts are written for whatever the run produced; the package
    artifact is written only when the run was valid, because an artifact that
    failed its gate must not exist where something might read it.

    Args:
        job_description: Raw posting text.
        evidence_source: Raw evidence text — a corpus file's content, or a
            markdown resume.
        evidence_format: ``"markdown"`` or ``"corpus"``.
        settings: Pipeline settings; packaged defaults are used if omitted.
        output_dir: Where to write artifacts. Nothing is written when omitted
            or when ``write_stage_artifacts`` is off.
        extractor: ``"lexical"`` or ``"llm"``.
        matcher: ``"lexical"`` or ``"llm"``.
        model: Provider for the strategy and question nodes, and for any stage
            set to ``"llm"``; one instance serves all of them.

    Returns:
        Final state, including ``prep_package`` when valid and
        ``validation_errors`` when not.
    """
    from ..config import load_settings

    settings = settings or load_settings()
    workflow = build_prep_workflow(
        extractor=_resolve_extractor(extractor, model),
        matcher=_resolve_matcher(matcher, model),
        model=model,
        search=search,
        match_threshold=settings.match_threshold,
        max_matches=settings.max_matches_per_requirement,
        min_requirements=settings.min_requirements,
        max_requirements=settings.max_requirements,
        min_requirement_chars=settings.min_requirement_chars,
        max_search_queries=settings.max_search_queries,
        max_research_findings=settings.max_research_findings,
    )
    state = workflow.invoke(
        {
            "job_description": job_description,
            "evidence_source": evidence_source,
            "evidence_format": evidence_format,
            "research_text": research_text,
            "company": company,
            "role_title": role_title,
        }
    )

    if output_dir is not None and settings.write_stage_artifacts:
        _write_prep_artifacts(Path(output_dir), state)

    return state


def _write_prep_artifacts(output_dir: Path, state: PrepState) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    _dump(
        output_dir / REQUIREMENTS_ARTIFACT,
        [item.model_dump(mode="json", exclude_none=True) for item in state.get("requirements", [])],
    )
    _dump(output_dir / DROPPED_ARTIFACT, list(state.get("dropped_requirements", []) or []))
    _dump(
        output_dir / MATCHES_ARTIFACT,
        [item.model_dump(mode="json") for item in state.get("matches", [])],
    )
    _dump(
        output_dir / FOCUS_AREAS_ARTIFACT,
        [item.model_dump(mode="json") for item in state.get("focus_areas", [])],
    )
    _dump(
        output_dir / RESEARCH_ARTIFACT,
        [
            item.model_dump(mode="json", exclude_none=True)
            for item in state.get("research_findings", []) or []
        ],
    )
    strategy = state.get("strategy")
    if strategy is not None:
        _dump(output_dir / STRATEGY_ARTIFACT, strategy.model_dump(mode="json"))
    _dump(
        output_dir / QUESTIONS_ARTIFACT,
        [item.model_dump(mode="json") for item in state.get("mock_questions", [])],
    )
    package = state.get("prep_package")
    if package is not None:
        _dump(
            output_dir / PACKAGE_ARTIFACT,
            package.model_dump(mode="json", exclude_none=True),
        )


__all__ = [
    "DROPPED_ARTIFACT",
    "EXTRACTORS",
    "FOCUS_AREAS_ARTIFACT",
    "LEXICAL",
    "MATCHERS",
    "MATCHES_ARTIFACT",
    "MODEL_BACKED",
    "PACKAGE_ARTIFACT",
    "PLAN_ARTIFACT",
    "QUESTIONS_ARTIFACT",
    "REQUIREMENTS_ARTIFACT",
    "RESEARCH_ARTIFACT",
    "STRATEGY_ARTIFACT",
    "run_pipeline",
    "run_prep",
    "run_workflow",
]

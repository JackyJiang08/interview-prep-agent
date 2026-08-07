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

from ..models import EvidenceItem, FocusPlan, Requirement, RequirementMatch
from ..providers import StructuredModel
from .extract import extract_requirements
from .extract_model import extract_requirements_with_model
from .gates import QualityGateError
from .graph import WorkflowState, build_workflow

REQUIREMENTS_ARTIFACT = "requirements.json"
MATCHES_ARTIFACT = "matches.json"
PLAN_ARTIFACT = "focus_plan.json"

LEXICAL = "lexical"
MODEL_BACKED = "llm"
EXTRACTORS = (LEXICAL, MODEL_BACKED)


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


def run_workflow(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    settings=None,
    extractor: str = LEXICAL,
    model: StructuredModel | None = None,
) -> WorkflowState:
    """Run the graph and return its final state.

    Requirement validation failures are reported in the returned state rather
    than raised, because routing on them is the graph's job.

    Args:
        job_description: Raw posting text.
        evidence: The candidate's evidence corpus.
        settings: Pipeline settings; packaged defaults are used if omitted.
        extractor: ``"lexical"`` or ``"llm"``.
        model: Provider used when ``extractor`` is ``"llm"``.

    Returns:
        Final state, including ``plan`` when valid and ``validation_errors``
        when not.
    """
    from ..config import load_settings

    settings = settings or load_settings()
    workflow = build_workflow(
        extractor=_resolve_extractor(extractor, model),
        match_threshold=settings.match_threshold,
        max_matches=settings.max_matches_per_requirement,
        min_requirements=settings.min_requirements,
        max_requirements=settings.max_requirements,
    )
    return workflow.invoke({"job_description": job_description, "evidence": list(evidence)})


def run_pipeline(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    settings=None,
    output_dir: Path | None = None,
    extractor: str = LEXICAL,
    model: StructuredModel | None = None,
) -> FocusPlan:
    """Run the workflow and return the plan.

    Args:
        job_description: Raw posting text.
        evidence: The candidate's evidence corpus.
        settings: Pipeline settings; packaged defaults are used if omitted.
        output_dir: Where to write per-stage artifacts. Nothing is written when
            omitted or when ``write_stage_artifacts`` is off.
        extractor: ``"lexical"`` or ``"llm"``.
        model: Provider used when ``extractor`` is ``"llm"``.

    Returns:
        The gap-first focus plan.

    Raises:
        QualityGateError: If extraction produced a requirement set that fails
            the grounding gate, or if matching lost or mis-cited anything.
    """
    from ..config import load_settings

    settings = settings or load_settings()
    state = run_workflow(job_description, evidence, settings, extractor, model)

    if not state.get("requirements_valid", False):
        raise QualityGateError("; ".join(state.get("validation_errors", [])))

    plan = state["plan"]
    if output_dir is not None and settings.write_stage_artifacts:
        _write_artifacts(Path(output_dir), state["requirements"], state["matches"], plan)
    return plan


def _write_artifacts(
    output_dir: Path,
    requirements: list[Requirement],
    verdicts: list[RequirementMatch],
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
    _dump(output_dir / PLAN_ARTIFACT, plan.model_dump(mode="json", exclude_none=True))


def _dump(path: Path, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


__all__ = [
    "EXTRACTORS",
    "LEXICAL",
    "MATCHES_ARTIFACT",
    "MODEL_BACKED",
    "PLAN_ARTIFACT",
    "REQUIREMENTS_ARTIFACT",
    "run_pipeline",
    "run_workflow",
]

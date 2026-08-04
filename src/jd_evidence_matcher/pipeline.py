"""End-to-end orchestration.

Control flow lives here, in code, not in a model. Each stage writes its own
artifact before the next one starts, so a bad plan can be traced back to the
stage that produced the bad input.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

from .config import Settings, load_settings
from .extract import extract_requirements
from .match import match_requirements
from .models import EvidenceItem, FocusPlan, Requirement, RequirementMatch
from .plan import build_focus_plan

REQUIREMENTS_ARTIFACT = "requirements.json"
MATCHES_ARTIFACT = "matches.json"
PLAN_ARTIFACT = "focus_plan.json"


def run_pipeline(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    settings: Optional[Settings] = None,
    output_dir: Optional[Path] = None,
) -> FocusPlan:
    """Run extraction, matching and planning over one posting.

    Args:
        job_description: Raw posting text.
        evidence: The candidate's evidence corpus.
        settings: Pipeline settings; the packaged defaults are used if omitted.
        output_dir: Where to write per-stage artifacts. Nothing is written when
            omitted or when ``write_stage_artifacts`` is off.

    Returns:
        The gap-first focus plan.
    """
    settings = settings or load_settings()

    requirements = extract_requirements(job_description)
    verdicts = match_requirements(
        requirements,
        evidence,
        threshold=settings.match_threshold,
        max_matches=settings.max_matches_per_requirement,
    )
    plan = build_focus_plan(requirements, verdicts, evidence)

    if output_dir is not None and settings.write_stage_artifacts:
        _write_artifacts(Path(output_dir), requirements, verdicts, plan)

    return plan


def _write_artifacts(
    output_dir: Path,
    requirements: List[Requirement],
    verdicts: List[RequirementMatch],
    plan: FocusPlan,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    _dump(output_dir / REQUIREMENTS_ARTIFACT, [item.model_dump() for item in requirements])
    _dump(output_dir / MATCHES_ARTIFACT, [item.model_dump(mode="json") for item in verdicts])
    _dump(output_dir / PLAN_ARTIFACT, plan.model_dump(mode="json"))


def _dump(path: Path, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

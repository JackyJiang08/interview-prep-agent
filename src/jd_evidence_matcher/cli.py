"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import load_settings
from .corpus import CorpusError, load_evidence, load_job_description
from .models import FocusPlan, Status
from .pipeline import run_pipeline
from .plan import QualityGateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jd-evidence-matcher",
        description=(
            "Extract requirements from a job description and label each one "
            "PROOF or GAP against an evidence corpus."
        ),
    )
    parser.add_argument("--jd", required=True, type=Path, help="job description text file")
    parser.add_argument("--evidence", required=True, type=Path, help="evidence corpus (YAML or JSON)")
    parser.add_argument("--out", type=Path, default=None, help="directory for stage artifacts")
    parser.add_argument("--config", type=Path, default=None, help="settings file")
    return parser


def render(plan: FocusPlan) -> str:
    """Render a focus plan as readable text."""
    lines = [
        "Coverage: {total} requirements | {proof} PROOF | {gap} GAP".format(
            total=plan.coverage.total,
            proof=plan.coverage.proof,
            gap=plan.coverage.gap,
        ),
        "Method: {}".format(plan.method),
        "",
    ]
    for item in plan.items:
        marker = "GAP " if item.status is Status.GAP else "PROOF"
        lines.append("[{}] {} {}".format(marker, item.requirement.id, item.requirement.text))
        lines.append("        {}".format(item.note))
        for match in item.matches:
            lines.append(
                "        - {} score={:.2f} terms={}".format(
                    match.evidence_id,
                    match.score,
                    ", ".join(match.overlapping_terms) or "none",
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        job_description = load_job_description(args.jd)
        evidence = load_evidence(args.evidence)
        settings = load_settings(args.config)
        plan = run_pipeline(job_description, evidence, settings, args.out)
    except (CorpusError, QualityGateError, OSError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1

    sys.stdout.write(render(plan))
    if args.out is not None:
        print("Stage artifacts written to {}".format(args.out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

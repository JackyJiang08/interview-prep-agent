"""Command-line interface.

Behaviour is organised into subcommands from the start, so that later
capabilities attach as siblings of ``match`` rather than by changing what an
existing invocation means.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_settings
from .corpus import CorpusError, load_evidence, load_job_description
from .models import FocusPlan, Status
from .providers import ProviderError, build_model
from .workflow import EXTRACTORS, LEXICAL, MODEL_BACKED, QualityGateError, run_pipeline

PROGRAM_NAME = "interview-prep-agent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="Evidence-grounded matching of job-description requirements.",
    )
    subcommands = parser.add_subparsers(dest="command", metavar="<command>")

    match = subcommands.add_parser(
        "match",
        help="label each requirement PROOF or GAP against an evidence corpus",
        description=(
            "Extract requirements from a job description and label each one "
            "PROOF or GAP against an evidence corpus."
        ),
    )
    match.add_argument("--jd", required=True, type=Path, help="job description text file")
    match.add_argument(
        "--evidence", required=True, type=Path, help="evidence corpus (YAML or JSON)"
    )
    match.add_argument("--out", type=Path, default=None, help="directory for stage artifacts")
    match.add_argument("--config", type=Path, default=None, help="settings file")
    match.add_argument(
        "--extractor",
        choices=EXTRACTORS,
        default=LEXICAL,
        help=(
            "how requirements are read from the posting. 'lexical' splits on "
            "list markers and needs no credentials; 'llm' calls a provider and "
            "needs GEMINI_API_KEY (default: lexical)"
        ),
    )
    match.set_defaults(handler=run_match)

    return parser


def render(plan: FocusPlan) -> str:
    """Render a focus plan as readable text."""
    coverage = plan.coverage
    lines = [
        f"Coverage: {coverage.total} requirements | {coverage.proof} PROOF | {coverage.gap} GAP",
        f"Method: {plan.method}",
        "",
    ]
    for item in plan.items:
        marker = "GAP " if item.status is Status.GAP else "PROOF"
        lines.append(f"[{marker}] {item.requirement.id} {item.requirement.text}")
        lines.append(f"        {item.note}")
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


def run_match(args: argparse.Namespace) -> int:
    """Handle the ``match`` subcommand."""
    try:
        job_description = load_job_description(args.jd)
        evidence = load_evidence(args.evidence)
        settings = load_settings(args.config)
        model = build_model() if args.extractor == MODEL_BACKED else None
        plan = run_pipeline(
            job_description,
            evidence,
            settings,
            args.out,
            extractor=args.extractor,
            model=model,
        )
    except (CorpusError, ProviderError, QualityGateError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(render(plan))
    if args.out is not None:
        print(f"Stage artifacts written to {args.out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2

    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

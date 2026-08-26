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
from .providers import DEFAULT_PROVIDER, PROVIDERS, ProviderError, build_model
from .search import maybe_build_search_provider
from .workflow import (
    EXTRACTORS,
    LEXICAL,
    MATCHERS,
    MODEL_BACKED,
    QualityGateError,
    run_pipeline,
    run_prep,
)

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
    match.add_argument(
        "--matcher",
        choices=MATCHERS,
        default=LEXICAL,
        help=(
            "how requirements are scored against evidence. 'lexical' uses "
            "IDF-weighted term overlap and needs no credentials; 'llm' asks a "
            "provider for coverage judgments and needs GEMINI_API_KEY "
            "(default: lexical)"
        ),
    )
    match.set_defaults(handler=run_match)

    prep = subcommands.add_parser(
        "prep",
        help="run the full preparation workflow to a validated package",
        description=(
            "Run the full workflow: extract requirements, match evidence, "
            "assess gaps, compose a strategy, generate practice questions, "
            "and assemble a validated preparation package. The strategy and "
            "question stages call a provider, so this command needs "
            "GEMINI_API_KEY."
        ),
    )
    prep.add_argument("--jd", required=True, type=Path, help="job description text file")
    prep.add_argument(
        "--evidence",
        required=True,
        type=Path,
        help="evidence corpus (.yaml/.json) or markdown resume (.md)",
    )
    prep.add_argument("--out", type=Path, default=None, help="directory for stage artifacts")
    prep.add_argument("--config", type=Path, default=None, help="settings file")
    prep.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER,
        help=f"model provider for every model stage (default: {DEFAULT_PROVIDER})",
    )
    prep.add_argument(
        "--research-file",
        type=Path,
        default=None,
        help=(
            "optional file of role research notes; informs strategy and "
            "questions only, never matching"
        ),
    )
    prep.add_argument(
        "--company",
        default="",
        help="the company, optional; names the research queries and reaches preparation only",
    )
    prep.add_argument(
        "--role-title",
        default="",
        help="the role title, optional; same reach as --company",
    )
    prep.add_argument(
        "--extractor",
        choices=EXTRACTORS,
        default=LEXICAL,
        help="requirement extraction path (default: lexical)",
    )
    prep.add_argument(
        "--matcher",
        choices=MATCHERS,
        default=LEXICAL,
        help="evidence matching path (default: lexical)",
    )
    prep.set_defaults(handler=run_prep_command)

    agent = subcommands.add_parser(
        "agent",
        help="run the bounded decision loop, pausing for answers when asked",
        description=(
            "Run the decision loop around the preparation workflow. The loop "
            "may interrupt with one focused factual question about a "
            "high-priority gap; the answer becomes first-class evidence and "
            "the package is regenerated over the enlarged corpus. The decide "
            "stage calls a provider, so this command needs GEMINI_API_KEY."
        ),
    )
    agent.add_argument("--jd", required=True, type=Path, help="job description text file")
    agent.add_argument(
        "--evidence",
        required=True,
        type=Path,
        help="evidence corpus (.yaml/.json) or markdown resume (.md)",
    )
    agent.add_argument("--out", type=Path, default=None, help="directory for artifacts")
    agent.add_argument("--config", type=Path, default=None, help="settings file")
    agent.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER,
        help=f"model provider for every model stage (default: {DEFAULT_PROVIDER})",
    )
    agent.add_argument(
        "--research-file",
        type=Path,
        default=None,
        help=(
            "optional file of role research notes; informs strategy and "
            "questions only, never matching"
        ),
    )
    agent.add_argument(
        "--company",
        default="",
        help="the company, optional; names the research queries and reaches preparation only",
    )
    agent.add_argument(
        "--role-title",
        default="",
        help="the role title, optional; same reach as --company",
    )
    agent.add_argument(
        "--extractor",
        choices=EXTRACTORS,
        default=LEXICAL,
        help="requirement extraction path (default: lexical)",
    )
    agent.add_argument(
        "--matcher",
        choices=MATCHERS,
        default=LEXICAL,
        help="evidence matching path (default: lexical)",
    )
    round_group = agent.add_mutually_exclusive_group()
    round_group.add_argument(
        "--round",
        default=None,
        help="freeform description of the upcoming interview round",
    )
    round_group.add_argument(
        "--round-file",
        type=Path,
        default=None,
        help="file containing the round description",
    )
    agent.set_defaults(handler=run_agent_command)

    evaluation = subcommands.add_parser(
        "eval",
        help="run the behavioral regression suites",
        description=(
            "Run the behavioral regression suites: scenario datasets with "
            "frozen trajectories, state deltas and outcomes, scored against "
            "the real compiled agent graph. This proves behavior did not "
            "silently change; it does not measure output quality."
        ),
    )
    evaluation.add_argument(
        "--suite",
        choices=("offline", "live"),
        required=True,
        help="offline runs fixture providers; live calls the real provider",
    )
    evaluation.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=DEFAULT_PROVIDER,
        help=f"model provider for the live suite (default: {DEFAULT_PROVIDER})",
    )
    evaluation.add_argument(
        "--experiment",
        default=None,
        help="experiment prefix for a remote run; defaults to the suite name",
    )
    evaluation.add_argument(
        "--local",
        action="store_true",
        help="print the scenario matrix locally without any remote experiment",
    )
    evaluation.set_defaults(handler=run_eval_command)

    serve = subcommands.add_parser(
        "serve",
        help="run the web session layer",
        description=(
            "Serve the web session layer: sessions over the agent with a "
            "WebSocket stream for interrupts and answers. Requires the "
            "server extra (pip install -r requirements-server.txt)."
        ),
    )
    serve.add_argument("--host", default="127.0.0.1", help="bind address")
    serve.add_argument("--port", type=int, default=8000, help="bind port")
    serve.add_argument("--config", type=Path, default=None, help="settings file")
    serve.set_defaults(handler=run_serve_command)

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
        needs_model = MODEL_BACKED in (args.extractor, args.matcher)
        model = build_model() if needs_model else None
        plan = run_pipeline(
            job_description,
            evidence,
            settings,
            args.out,
            extractor=args.extractor,
            model=model,
            matcher=args.matcher,
        )
    except (CorpusError, ProviderError, QualityGateError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(render(plan))
    if args.out is not None:
        print(f"Stage artifacts written to {args.out}", file=sys.stderr)
    return 0


def run_prep_command(args: argparse.Namespace) -> int:
    """Handle the ``prep`` subcommand."""
    try:
        job_description = load_job_description(args.jd)
        evidence_source = Path(args.evidence).read_text(encoding="utf-8")
        evidence_format = (
            "markdown" if Path(args.evidence).suffix.lower() in (".md", ".markdown") else "corpus"
        )
        settings = load_settings(args.config)
        research_text = (
            Path(args.research_file).read_text(encoding="utf-8")
            if args.research_file is not None
            else ""
        )
        # The strategy and question stages always call a provider, so the
        # credentials are required up front rather than failing three stages in.
        model = build_model(args.provider)
        state = run_prep(
            job_description,
            evidence_source,
            evidence_format,
            settings,
            args.out,
            extractor=args.extractor,
            matcher=args.matcher,
            model=model,
            research_text=research_text,
            search=maybe_build_search_provider(),
            company=args.company,
            role_title=args.role_title,
        )
    except (CorpusError, ProviderError, QualityGateError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if not state.get("package_valid", False):
        print("The package failed validation and was not assembled:", file=sys.stderr)
        for item in state.get("validation_errors", []):
            print(f"  - {item}", file=sys.stderr)
        return 1

    package = state["prep_package"]
    print(
        f"Package assembled: {len(package.requirements)} requirements | "
        f"{len(package.focus_areas)} focus areas | "
        f"{len(package.mock_questions)} questions"
    )
    if args.out is not None:
        print(f"Artifacts written to {args.out}", file=sys.stderr)
    return 0


def run_agent_command(args: argparse.Namespace) -> int:
    """Handle the ``agent`` subcommand."""
    from .agent import run_agent
    from .workflow.pipeline import _resolve_extractor, _resolve_matcher

    def ask_on_stdin(requirement_id: str, question: str) -> str:
        print(f"\nThe loop needs one fact about {requirement_id}:")
        print(f"  {question}")
        return input("> ").strip()

    try:
        job_description = load_job_description(args.jd)
        evidence_source = Path(args.evidence).read_text(encoding="utf-8")
        evidence_format = (
            "markdown" if Path(args.evidence).suffix.lower() in (".md", ".markdown") else "corpus"
        )
        round_text = args.round or ""
        if args.round_file is not None:
            round_text = Path(args.round_file).read_text(encoding="utf-8")
        research_text = (
            Path(args.research_file).read_text(encoding="utf-8")
            if args.research_file is not None
            else ""
        )
        settings = load_settings(args.config)
        # The workflow's preparation stages and the answer assessment always
        # call a provider, so the credentials are required up front.
        model = build_model(args.provider)
        state, _trace = run_agent(
            job_description,
            evidence_source,
            evidence_format,
            ask_on_stdin,
            settings,
            args.out,
            model=model,
            extractor=_resolve_extractor(args.extractor, model),
            matcher=_resolve_matcher(args.matcher, model),
            round_text=round_text,
            research_text=research_text,
            search=maybe_build_search_provider(),
            company=args.company,
            role_title=args.role_title,
        )
    except (CorpusError, ProviderError, QualityGateError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    stop_reason = state.get("stop_reason") or "none"
    print(f"Stopped: {stop_reason} after {state.get('action_count', 0)} action(s)")
    if state.get("package_valid") and state.get("prep_package") is not None:
        package = state["prep_package"]
        print(
            f"Package assembled: {len(package.requirements)} requirements | "
            f"{len(package.focus_areas)} focus areas | "
            f"{len(package.mock_questions)} questions"
        )
    else:
        for item in state.get("validation_errors", []):
            print(f"  - {item}", file=sys.stderr)
    if args.out is not None:
        print(f"Artifacts written to {args.out}", file=sys.stderr)
    return 0 if state.get("stop_reason") == "valid_package_complete" else 1


def run_eval_command(args: argparse.Namespace) -> int:
    """Handle the ``eval`` subcommand."""
    if args.local and args.suite != "offline":
        print("error: --local is supported only by the offline suite", file=sys.stderr)
        return 2

    # Imported lazily: the suites need agentevals, which is a development
    # dependency, and the remote path needs credentials the offline one never
    # touches.
    from .evals import runner

    try:
        if args.local:
            all_green = runner.run_local(args.suite, provider=args.provider)
        else:
            all_green = runner.run_remote(
                args.suite, args.experiment or args.suite, provider=args.provider
            )
    except (ProviderError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0 if all_green else 1


def run_serve_command(args: argparse.Namespace) -> int:
    """Handle the ``serve`` subcommand."""
    try:
        import uvicorn

        from .server import create_app
    except ImportError:
        print(
            "error: the server extra is not installed; run "
            "'pip install -r requirements-server.txt'",
            file=sys.stderr,
        )
        return 1

    settings = load_settings(args.config)
    uvicorn.run(create_app(settings), host=args.host, port=args.port)
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

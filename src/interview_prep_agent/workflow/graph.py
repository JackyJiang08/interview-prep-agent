"""The workflow as a state graph.

    START -> extract -> validate_requirements
                          |- valid   -> match -> assess -> plan -> assemble -> END
                          |- invalid -> report_errors -> END

Moving to a graph runtime changes how the stages are wired, not who decides.
Every node is a function of the state it is given; the one branch in the graph
is chosen by :func:`route_after_validation`, which reads a boolean that
deterministic code wrote.

**Why this is still not an agent.** Two things would have to be true for that
word to apply, and neither is. First, the set of branches would have to be open
at run time; here both targets are declared when the graph is built and nothing
can add a third. Second, the choice would have to be made by a model reasoning
over the state; here the predicate is a pure function this repo owns, returning
one of two literals from a field that gate code computed. A model does appear
inside the extract node when the model-backed path is selected, but it produces
*data* that is then validated — it never selects the next node. Control flow is
still fixed; the graph makes it explicit rather than implicit in call order.

State carries business values only: the inputs, the validated intermediates,
the plan, and the validation outcome. Raw provider responses, timings and trace
data are deliberately absent, so that reading the state tells you what the
system concluded rather than how it was produced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ..corpus import CorpusError, parse_evidence_corpus, parse_evidence_markdown
from ..models import (
    EvidenceItem,
    FocusArea,
    FocusPlan,
    InterviewStrategy,
    MockQuestion,
    PrepPackage,
    Requirement,
    RequirementMatch,
)
from ..providers import StructuredModel
from .assess import build_focus_areas
from .extract import extract_requirements
from .gates import (
    check_matches,
    check_requirements,
    collect_package_errors,
    collect_requirement_errors,
)
from .match import match_requirements
from .plan import build_focus_plan
from .questions import generate_questions_with_model
from .strategy import build_strategy_with_model

Extractor = Callable[[str], list[Requirement]]
Matcher = Callable[[list[Requirement], list[EvidenceItem]], list[RequirementMatch]]


class WorkflowState(TypedDict, total=False):
    """Business state shared by the nodes.

    Inputs are supplied at entry; every other field is written by exactly one
    node, so an unexpected value can be attributed to the node that wrote it.
    """

    # inputs
    job_description: str
    evidence: list[EvidenceItem]
    # grounded intermediates
    requirements: list[Requirement]
    matches: list[RequirementMatch]
    focus_areas: list[FocusArea]
    plan: FocusPlan | None
    # reliability
    validation_errors: list[str]
    requirements_valid: bool
    status: str


class WorkflowInput(TypedDict):
    """Values the caller supplies when the graph starts."""

    job_description: str
    evidence: list[EvidenceItem]


def build_workflow(
    extractor: Extractor = extract_requirements,
    matcher: Matcher | None = None,
    match_threshold: float = 0.30,
    max_matches: int = 3,
    min_requirements: int = 1,
    max_requirements: int = 50,
):
    """Compile the workflow.

    Args:
        extractor: Stage 1 implementation. Defaults to the lexical splitter;
            the model-backed path is injected here rather than selected inside
            a node, so the graph shape is identical either way.
        matcher: Stage 2 implementation, same injection pattern. Defaults to
            the lexical scorer configured with ``match_threshold`` and
            ``max_matches``; those two settings are ignored when a matcher is
            supplied, because the caller has already configured it.
        match_threshold: Minimum score for a requirement to count as supported.
        max_matches: Cap on evidence items cited per requirement.
        min_requirements: Fewest requirements a run may produce.
        max_requirements: Most requirements a run may produce.

    Returns:
        A compiled graph accepting ``WorkflowInput``.
    """

    def extract(state: WorkflowState) -> dict[str, Any]:
        return {"requirements": extractor(state["job_description"])}

    def validate_requirements(state: WorkflowState) -> dict[str, Any]:
        errors = collect_requirement_errors(
            state["job_description"],
            state.get("requirements", []),
            min_requirements=min_requirements,
            max_requirements=max_requirements,
        )
        return {"validation_errors": errors, "requirements_valid": not errors}

    def match(state: WorkflowState) -> dict[str, Any]:
        if matcher is not None:
            verdicts = matcher(state["requirements"], state["evidence"])
        else:
            verdicts = match_requirements(
                state["requirements"],
                state["evidence"],
                threshold=match_threshold,
                max_matches=max_matches,
            )
        # Both matcher paths face the same deterministic guard, and a failure
        # raises: a verdict set that lost a requirement or cited unknown
        # evidence must not reach assessment, and no substitute is fetched in
        # its place (see docs/DECISIONS.md on the absence of fallbacks).
        check_matches(state["requirements"], verdicts, state["evidence"])
        return {"matches": verdicts}

    def assess(state: WorkflowState) -> dict[str, Any]:
        return {"focus_areas": build_focus_areas(state["requirements"], state["matches"])}

    def plan(state: WorkflowState) -> dict[str, Any]:
        return {
            "plan": build_focus_plan(
                state["requirements"],
                state["matches"],
                state["evidence"],
                focus_areas=state["focus_areas"],
            )
        }

    def assemble(_state: WorkflowState) -> dict[str, Any]:
        return {"status": "complete"}

    def report_errors(_state: WorkflowState) -> dict[str, Any]:
        """End the run without a plan, leaving the errors in place."""
        return {"status": "invalid", "plan": None}

    builder = StateGraph(WorkflowState, input_schema=WorkflowInput)
    builder.add_node("extract", extract)
    builder.add_node("validate_requirements", validate_requirements)
    builder.add_node("match", match)
    builder.add_node("assess", assess)
    builder.add_node("plan", plan)
    builder.add_node("assemble", assemble)
    builder.add_node("report_errors", report_errors)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "validate_requirements")
    builder.add_conditional_edges(
        "validate_requirements",
        route_after_validation,
        {"valid": "match", "invalid": "report_errors"},
    )
    builder.add_edge("match", "assess")
    builder.add_edge("assess", "plan")
    builder.add_edge("plan", "assemble")
    builder.add_edge("assemble", END)
    builder.add_edge("report_errors", END)
    return builder.compile()


def route_after_validation(state: WorkflowState) -> Literal["valid", "invalid"]:
    """Pick a branch from the validation outcome.

    A pure function of one boolean that gate code wrote. It reads no other
    state, calls nothing, and can return only the two literals wired into the
    graph above.
    """
    return "valid" if state.get("requirements_valid") else "invalid"


class PrepState(TypedDict, total=False):
    """Business state for the full preparation graph.

    Same discipline as ``WorkflowState``: inputs at entry, every other field
    written by exactly one node, nothing about how a value was produced.
    """

    # inputs
    job_description: str
    evidence_source: str
    evidence_format: str
    # derived source evidence
    evidence: list[EvidenceItem]
    # grounded intermediates
    requirements: list[Requirement]
    matches: list[RequirementMatch]
    focus_areas: list[FocusArea]
    # preparation outputs
    strategy: InterviewStrategy | None
    mock_questions: list[MockQuestion]
    prep_package: PrepPackage | None
    # reliability
    validation_errors: list[str]
    package_valid: bool
    status: str


class PrepInput(TypedDict):
    """Values the caller supplies when the preparation graph starts."""

    job_description: str
    evidence_source: str
    evidence_format: str


def build_prep_workflow(
    extractor: Extractor = extract_requirements,
    matcher: Matcher | None = None,
    model: StructuredModel | None = None,
    match_threshold: float = 0.30,
    max_matches: int = 3,
    min_requirements: int = 1,
    max_requirements: int = 50,
    min_questions: int = 8,
):
    """Compile the full preparation workflow.

        START -> validate_inputs -> extract_evidence -> extract_requirements
              -> match -> assess_gaps -> build_strategy -> generate_questions
              -> validate_package -|- valid   -> assemble_package -> END
                                   |- invalid -> report_errors    -> END

    The same argument as ``build_workflow``, extended over more nodes: both
    branch targets are fixed when the graph is built, the routing predicate is
    a pure function over a boolean that deterministic gate code computed, and
    the models inside build_strategy and generate_questions produce data that
    the package gate then judges — no model ever selects the next node, and no
    model approves its own output.

    Deterministic guards raise inside the nodes that can violate them
    (extraction grounding, match consistency); the composed and generated
    layers are judged once, at validate_package, so a shortfall there routes
    to the error report instead of aborting — the run ends with its errors
    listed, which is a result, not a crash.

    Args:
        extractor: Stage 1 implementation; defaults to the lexical splitter.
        matcher: Stage 2 implementation; None selects the lexical scorer.
        model: Provider for the strategy and question nodes. Resolved lazily
            when omitted, so the graph itself compiles offline.
        match_threshold: Minimum score for the lexical matcher.
        max_matches: Citation cap per requirement for the lexical matcher.
        min_requirements: Fewest requirements a run may produce.
        max_requirements: Most requirements a run may produce.
        min_questions: Question floor enforced by the package gate.

    Returns:
        A compiled graph accepting ``PrepInput``.
    """

    def resolve_model() -> StructuredModel:
        if model is not None:
            return model
        from ..providers import build_model

        return build_model()

    def validate_inputs(state: PrepState) -> dict[str, Any]:
        if not state["job_description"].strip():
            raise CorpusError("the job description is empty")
        if not state["evidence_source"].strip():
            raise CorpusError("the evidence source is empty")
        return {}

    def extract_evidence(state: PrepState) -> dict[str, Any]:
        if state["evidence_format"] == "markdown":
            items = parse_evidence_markdown(state["evidence_source"])
        else:
            items = parse_evidence_corpus(state["evidence_source"], "the supplied evidence")
        return {"evidence": items}

    def extract_requirements_node(state: PrepState) -> dict[str, Any]:
        requirements = extractor(state["job_description"])
        check_requirements(
            state["job_description"],
            requirements,
            min_requirements=min_requirements,
            max_requirements=max_requirements,
        )
        return {"requirements": requirements}

    def match(state: PrepState) -> dict[str, Any]:
        if matcher is not None:
            verdicts = matcher(state["requirements"], state["evidence"])
        else:
            verdicts = match_requirements(
                state["requirements"],
                state["evidence"],
                threshold=match_threshold,
                max_matches=max_matches,
            )
        check_matches(state["requirements"], verdicts, state["evidence"])
        return {"matches": verdicts}

    def assess_gaps(state: PrepState) -> dict[str, Any]:
        return {"focus_areas": build_focus_areas(state["requirements"], state["matches"])}

    def build_strategy(state: PrepState) -> dict[str, Any]:
        return {
            "strategy": build_strategy_with_model(
                state["requirements"],
                state["matches"],
                state["focus_areas"],
                resolve_model(),
            )
        }

    def generate_questions(state: PrepState) -> dict[str, Any]:
        return {
            "mock_questions": generate_questions_with_model(
                state["requirements"],
                state["matches"],
                state["strategy"],
                resolve_model(),
            )
        }

    def validate_package(state: PrepState) -> dict[str, Any]:
        errors = collect_package_errors(
            state["job_description"],
            state.get("evidence", []),
            state.get("requirements", []),
            state.get("matches", []),
            state.get("focus_areas", []),
            state.get("strategy"),
            state.get("mock_questions", []),
            min_questions=min_questions,
        )
        return {"validation_errors": errors, "package_valid": not errors}

    def assemble_package(state: PrepState) -> dict[str, Any]:
        return {
            "status": "complete",
            "prep_package": PrepPackage(
                requirements=state["requirements"],
                matches=state["matches"],
                focus_areas=state["focus_areas"],
                strategy=state["strategy"],
                mock_questions=state["mock_questions"],
            ),
        }

    def report_errors(_state: PrepState) -> dict[str, Any]:
        """End the run without a package, leaving the errors in place."""
        return {"status": "invalid", "prep_package": None}

    builder = StateGraph(PrepState, input_schema=PrepInput)
    builder.add_node("validate_inputs", validate_inputs)
    builder.add_node("extract_evidence", extract_evidence)
    builder.add_node("extract_requirements", extract_requirements_node)
    builder.add_node("match", match)
    builder.add_node("assess_gaps", assess_gaps)
    builder.add_node("build_strategy", build_strategy)
    builder.add_node("generate_questions", generate_questions)
    builder.add_node("validate_package", validate_package)
    builder.add_node("assemble_package", assemble_package)
    builder.add_node("report_errors", report_errors)

    builder.add_edge(START, "validate_inputs")
    builder.add_edge("validate_inputs", "extract_evidence")
    builder.add_edge("extract_evidence", "extract_requirements")
    builder.add_edge("extract_requirements", "match")
    builder.add_edge("match", "assess_gaps")
    builder.add_edge("assess_gaps", "build_strategy")
    builder.add_edge("build_strategy", "generate_questions")
    builder.add_edge("generate_questions", "validate_package")
    builder.add_conditional_edges(
        "validate_package",
        route_after_package,
        {"valid": "assemble_package", "invalid": "report_errors"},
    )
    builder.add_edge("assemble_package", END)
    builder.add_edge("report_errors", END)
    return builder.compile()


def route_after_package(state: PrepState) -> Literal["valid", "invalid"]:
    """Pick a branch from the package validation outcome.

    A pure function of one boolean that gate code wrote, returning one of the
    two literals wired into the graph above.
    """
    return "valid" if state.get("package_valid") else "invalid"


# Module-level compiled graphs, for local graph tooling. The preparation graph
# compiles offline; its model nodes resolve a provider only when they run.
graph = build_workflow()
prep_graph = build_prep_workflow()

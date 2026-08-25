"""The evidence-gated human-in-the-loop layer around the preparation workflow.

    START -> parse_round -> generate_initial -> observe
                                                  |- ask -> assess -> observe
                                                  |- generate_final -> END
                                                  |- invalid -> END

There is no decide node. When the rule became "process every gap exactly once
in a deterministic order," the next action stopped being a decision and became
a computable function — and autonomy proportional to the decision cuts both
ways, so routing returned to pure code. The model's judgment now lives in the
two places code genuinely cannot judge: what kind of interview round a
freeform description denotes, and whether a human's answer actually evidences
a requirement. Both sit behind code-owned gates: the parsed round reaches only
the preparation prompts, and an assessment is advice that the admission gate —
answer length, target identity, validity, a non-empty admitted claim — must
approve before anything becomes evidence.

Admitted answers mint ``CL-`` evidence whose summary is the admitted claim,
not the raw answer, so nothing stronger than what the gate approved can ever
be cited. Rejected answers change audit state only; the requirement stays a
gap. Neither generation writes anything to disk — artifacts are the runner's
job, and only the final state produces them.
"""

from __future__ import annotations

import json
import operator
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import yaml
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .corpus import clarification_to_evidence, parse_evidence_corpus, parse_evidence_markdown
from .models import (
    Clarification,
    ClarificationAssessment,
    ClarificationRecord,
    CoverageLevel,
    EvidenceItem,
    FocusArea,
    InterviewRound,
    InterviewStrategy,
    MockQuestion,
    PrepPackage,
    Requirement,
    RequirementMatch,
    ResearchFinding,
)
from .providers import ProviderError, StructuredModel
from .workflow.extract import extract_requirements
from .workflow.graph import Extractor, Matcher, build_prep_workflow

STOP_VALID_PACKAGE = "valid_package_complete"
STOP_INVALID_INITIAL = "invalid_initial_package"
STOP_INVALID_FINAL = "invalid_final_package"
STOP_BUDGET_EXHAUSTED = "action_budget_exhausted"

CEILING_NOTE = "question ceiling reached with gaps remaining"

# Business fields copied back from a workflow run. Nothing else crosses:
# the workflow's own control fields stay its own.
WORKFLOW_RESULT_FIELDS = (
    "evidence",
    "research_findings",
    "requirements",
    "matches",
    "focus_areas",
    "strategy",
    "mock_questions",
    "prep_package",
    "validation_errors",
    "package_valid",
)

ROUND_PARSING_INSTRUCTIONS = """\
You parse a freeform description of an upcoming interview round.

Extract only details explicitly present in the text. Do not infer missing
facts, do not guess a format from a role, and do not fill conventional
defaults. Leave optional strings null and optional lists empty when the text
does not supply them.

Return nothing except data conforming to the supplied schema.
"""

ASSESSMENT_INSTRUCTIONS = """\
You assess whether one candidate answer may be admitted as evidence for
exactly one job requirement.

Rubric:

- target_requirement_id must exactly match the supplied requirement's
  identifier.
- is_valid may be true only when the answer directly addresses the
  requirement with a concrete first-person claim about what the candidate
  actually did.
- Reject vague interest, plans to learn, unsupported self-ratings, unrelated
  experience, and answers that merely restate the requirement.
- accepted_claim must be a concise, faithful restatement of facts explicitly
  in the answer. Never strengthen, infer, or invent. When is_valid is false,
  accepted_claim must be null.

Return nothing except data conforming to the supplied schema.
"""


class AgentState(TypedDict, total=False):
    """Workflow business state plus queue, admission and audit state.

    The additive lists exist because the interrupt node restarts on resume;
    additive updates are what make that restart safe.
    """

    # source inputs
    job_description: str
    evidence_source: str
    evidence_format: str
    round_text: str
    research_text: str
    # round context, parsed once
    round_context: InterviewRound | None
    # admission and audit, additive
    clarifications: Annotated[list[Clarification], operator.add]
    clarification_evidence: Annotated[list[EvidenceItem], operator.add]
    clarification_records: Annotated[list[ClarificationRecord], operator.add]
    processed_requirement_ids: Annotated[list[str], operator.add]
    # workflow-derived business state
    evidence: list[EvidenceItem]
    research_findings: list[ResearchFinding]
    requirements: list[Requirement]
    matches: list[RequirementMatch]
    focus_areas: list[FocusArea]
    strategy: InterviewStrategy | None
    mock_questions: list[MockQuestion]
    prep_package: PrepPackage | None
    validation_errors: list[str]
    package_valid: bool
    # loop control
    current_gap: Requirement | None
    current_question: str | None
    pending_answer: str | None
    question_budget_left: bool
    initial_gap_count: int
    action_count: int
    initial_package_generated: bool
    final_note: str | None
    stop_reason: str | None


class AgentInput(TypedDict):
    """Values the caller supplies when the loop starts."""

    job_description: str
    evidence_source: str
    evidence_format: str
    round_text: str
    research_text: str


def select_next_gap(
    requirements: list[Requirement],
    verdicts: list[RequirementMatch],
    processed_requirement_ids: list[str],
) -> Requirement | None:
    """Select the next gap in the deterministic processing order.

    Eligible gaps are verdicts at GAP coverage whose requirement is known and
    not yet processed — processed means asked once, not resolved. They are
    sorted by importance descending, with missing importance sorting last,
    then by requirement identifier ascending so ties are stable and
    explainable. Returns ``None`` when the queue is empty.
    """
    by_id = {item.id: item for item in requirements}
    processed = set(processed_requirement_ids)

    queue = [
        by_id[verdict.requirement_id]
        for verdict in verdicts
        if verdict.coverage is CoverageLevel.GAP
        and verdict.requirement_id in by_id
        and verdict.requirement_id not in processed
    ]
    queue.sort(key=lambda item: (-(item.importance or 0), item.id))
    return queue[0] if queue else None


def admission_failure(
    answer: str,
    assessment: ClarificationAssessment,
    target_requirement_id: str,
    min_clarification_length: int,
) -> str | None:
    """Apply every code-owned evidence-admission gate to one answer.

    Returns the first failure, or ``None`` when the answer may be admitted.
    The gates run in order of cheapness and trust: the length floor needs no
    model at all; the target check means model output cannot redirect
    evidence to a requirement that was never asked about; only then do the
    assessment's own verdict and its admitted claim count.
    """
    if len(answer.strip()) < min_clarification_length:
        return f"admission: the answer must contain at least {min_clarification_length} characters"
    if assessment.target_requirement_id != target_requirement_id:
        return (
            f"admission: the assessment targeted "
            f"{assessment.target_requirement_id}, not the requirement asked "
            f"({target_requirement_id})"
        )
    if not assessment.is_valid:
        return (
            "admission: the assessment rejected the answer — "
            f"{assessment.relevance_reason} {assessment.specificity_reason}"
        )
    if not assessment.accepted_claim or not assessment.accepted_claim.strip():
        return "admission: a valid assessment must carry a non-empty accepted claim"
    return None


def should_admit(
    answer: str,
    assessment: ClarificationAssessment,
    target_requirement_id: str,
    min_clarification_length: int,
) -> bool:
    """Boolean form of :func:`admission_failure`; one implementation."""
    return (
        admission_failure(answer, assessment, target_requirement_id, min_clarification_length)
        is None
    )


def build_question(gap: Requirement) -> str:
    """Build the one focused factual question for a gap, in code."""
    return (
        "Share one specific example from your experience that demonstrates "
        f"this requirement: {gap.text}. Include what you did, the method or "
        "tools you used, and the result."
    )


def build_round_parsing_prompt(round_text: str) -> str:
    """Place the freeform round text after the parsing instructions."""
    return f"{ROUND_PARSING_INSTRUCTIONS}\n----- ROUND DESCRIPTION -----\n{round_text}\n"


def build_assessment_prompt(gap: Requirement, question: str, answer: str) -> str:
    """Build the short-context assessment prompt: one requirement, one answer.

    Deliberately narrow — the assessor sees the target requirement, the
    question and the answer, not the whole run, so its advice cannot be
    steered by anything except the exchange it is judging.
    """
    target = {"requirement_id": gap.id, "requirement": gap.text}
    return (
        f"{ASSESSMENT_INSTRUCTIONS}\n"
        "----- TARGET REQUIREMENT -----\n"
        f"{json.dumps(target, indent=2, ensure_ascii=False)}\n"
        "----- QUESTION -----\n"
        f"{question}\n"
        "----- CANDIDATE ANSWER -----\n"
        f"{answer}\n"
    )


def route_after_observation(
    state: AgentState,
) -> Literal["ask", "generate_final", "invalid"]:
    """Route from code-owned package validity, queue state and budgets.

    Pure function; every input it reads was computed by deterministic code.
    An invalid initial package and an exhausted action budget terminate with
    their own stop reasons; an exhausted question ceiling with gaps remaining
    proceeds to final generation, noted in the trace — exhaustion terminates
    a phase, never raises.
    """
    if not state.get("package_valid", False):
        return "invalid"
    if state.get("stop_reason") == STOP_BUDGET_EXHAUSTED:
        return "invalid"
    if state.get("current_gap") is not None and state.get("question_budget_left", True):
        return "ask"
    return "generate_final"


def build_agent_graph(
    model: StructuredModel | None = None,
    checkpointer: Any = None,
    extractor: Extractor = extract_requirements,
    matcher: Matcher | None = None,
    search: Any = None,
    max_agent_actions: int | None = None,
    agent_action_cap: int = 32,
    max_questions_per_run: int | None = None,
    min_clarification_length: int = 24,
    max_search_queries: int = 3,
    max_research_findings: int = 12,
    match_threshold: float = 0.30,
    max_matches: int = 3,
    min_requirements: int = 1,
    max_requirements: int = 50,
    min_questions: int = 8,
):
    """Compile the evidence-gated loop.

    Control flow is entirely code-owned: every branch target is fixed at
    build time and the one conditional routes on package validity, the
    deterministic gap queue, and budgets. The model is consulted for data at
    exactly three points — the optional round parse, the workflow's
    preparation stages, and the per-answer assessment — and each of its
    outputs faces a code-owned gate before it can affect anything.

    Args:
        model: Provider for the model stages. Resolved lazily when omitted,
            so the graph compiles offline.
        checkpointer: Required for interrupt and resume.
        extractor: Stage 1 implementation for the inner workflow.
        matcher: Stage 2 implementation for the inner workflow.
        max_agent_actions: Action budget; ``None`` derives it from the gap
            queue plus the two generation runs.
        agent_action_cap: Hard clamp on the derived or configured budget.
        max_questions_per_run: Question ceiling; ``None`` means every gap
            exactly once.
        min_clarification_length: Answer floor enforced before any model
            judgment is consulted.
        match_threshold: Lexical matcher threshold, passed through.
        max_matches: Citation cap, passed through.
        min_requirements: Extraction floor, passed through.
        max_requirements: Extraction ceiling, passed through.
        min_questions: Package-gate question floor, passed through.

    Returns:
        A compiled graph accepting ``AgentInput``.
    """

    def resolve_model() -> StructuredModel:
        if model is not None:
            return model
        from .providers import build_model

        return build_model()

    workflow = build_prep_workflow(
        extractor=extractor,
        matcher=matcher,
        model=model,
        search=search,
        match_threshold=match_threshold,
        max_matches=max_matches,
        min_requirements=min_requirements,
        max_requirements=max_requirements,
        min_questions=min_questions,
        max_search_queries=max_search_queries,
        max_research_findings=max_research_findings,
    )

    def effective_action_budget(state: AgentState) -> int:
        derived = (
            max_agent_actions
            if max_agent_actions is not None
            else state.get("initial_gap_count", 0) + 2
        )
        return min(derived, agent_action_cap)

    def parse_round(state: AgentState) -> dict[str, Any]:
        """Parse optional freeform round text, once, before any generation."""
        round_text = (state.get("round_text") or "").strip()
        if not round_text:
            return {"round_context": None}
        payload = resolve_model().generate_json(
            build_round_parsing_prompt(round_text), InterviewRound.model_json_schema()
        )
        try:
            parsed = InterviewRound.model_validate(payload, from_attributes=True)
        except Exception as error:  # noqa: BLE001 - pydantic raises several types
            raise ProviderError(
                f"model response did not match the requested schema: {error}"
            ) from error
        return {"round_context": parsed}

    def run_workflow_once(state: AgentState) -> dict[str, Any]:
        if state["evidence_format"] == "markdown":
            base = parse_evidence_markdown(state["evidence_source"])
        else:
            base = parse_evidence_corpus(state["evidence_source"], "the supplied evidence")
        corpus = [*base, *state.get("clarification_evidence", [])]
        source = yaml.safe_dump(
            [item.model_dump(exclude_none=True) for item in corpus],
            sort_keys=False,
            allow_unicode=True,
        )
        result = workflow.invoke(
            {
                "job_description": state["job_description"],
                "evidence_source": source,
                "evidence_format": "corpus",
                "round_context": state.get("round_context"),
                "research_text": state.get("research_text", ""),
            }
        )
        return {field: result.get(field) for field in WORKFLOW_RESULT_FIELDS}

    def generate_initial(state: AgentState) -> dict[str, Any]:
        """One full workflow run; the package is not written anywhere."""
        update = run_workflow_once(state)
        update["initial_package_generated"] = True
        update["action_count"] = state.get("action_count", 0) + 1
        return update

    def observe(state: AgentState) -> dict[str, Any]:
        """Pure selection of the next queue item and the budget state."""
        current = select_next_gap(
            state.get("requirements", []),
            state.get("matches", []),
            state.get("processed_requirement_ids", []),
        )
        asked = len(state.get("processed_requirement_ids", []))
        budget_left = max_questions_per_run is None or asked < max_questions_per_run
        update: dict[str, Any] = {
            "current_gap": current,
            "question_budget_left": budget_left,
        }
        if "initial_gap_count" not in state:
            gap_count = sum(
                1 for verdict in state.get("matches", []) if verdict.coverage is CoverageLevel.GAP
            )
            update["initial_gap_count"] = gap_count
        if state.get("action_count", 0) >= effective_action_budget({**state, **update}):
            update["stop_reason"] = STOP_BUDGET_EXHAUSTED
        return update

    def ask(state: AgentState) -> dict[str, Any]:
        """Interrupt for one answer; stage it and nothing else.

        Everything before ``interrupt()`` must stay idempotent: the node
        restarts from its top on resume, and only the staging fields change
        here — admission happens in the next node.
        """
        gap = state.get("current_gap")
        if gap is None:
            raise ValueError("the ask capability requires a current gap")
        question = build_question(gap)
        answer = interrupt(
            {
                "type": "evidence_request",
                "requirement_id": gap.id,
                "question": question,
            }
        )
        return {
            "current_question": question,
            "pending_answer": str(answer).strip(),
            "action_count": state.get("action_count", 0) + 1,
        }

    def assess_and_admit(state: AgentState) -> dict[str, Any]:
        """One short-context assessment, then the code-owned admission gate."""
        gap = state.get("current_gap")
        question = state.get("current_question")
        answer = state.get("pending_answer")
        if gap is None or question is None or answer is None:
            raise ValueError("assessment requires a gap, a question and an answer")

        payload = resolve_model().generate_json(
            build_assessment_prompt(gap, question, answer),
            ClarificationAssessment.model_json_schema(),
        )
        try:
            assessment = ClarificationAssessment.model_validate(payload, from_attributes=True)
        except Exception as error:  # noqa: BLE001 - pydantic raises several types
            raise ProviderError(
                f"model response did not match the requested schema: {error}"
            ) from error

        failure = admission_failure(answer, assessment, gap.id, min_clarification_length)
        accepted = failure is None
        accepted_claim = assessment.accepted_claim if accepted else None
        record = ClarificationRecord(
            requirement_id=gap.id,
            question=question,
            answer=answer,
            assessment=assessment,
            accepted=accepted,
            decision_reason=failure or "every code-owned admission gate passed",
            accepted_claim=accepted_claim,
        )
        update: dict[str, Any] = {
            "processed_requirement_ids": [gap.id],
            "clarification_records": [record],
            "pending_answer": None,
            "current_question": None,
        }
        if accepted and accepted_claim is not None:
            clarification = Clarification(
                requirement_id=gap.id,
                question=question,
                answer=answer,
                accepted_claim=accepted_claim,
            )
            update["clarifications"] = [clarification]
            update["clarification_evidence"] = [
                clarification_to_evidence(clarification, len(state.get("clarifications", [])) + 1)
            ]
        return update

    def generate_final(state: AgentState) -> dict[str, Any]:
        """One final full-context run over corpus, admitted evidence, round."""
        update = run_workflow_once(state)
        update["action_count"] = state.get("action_count", 0) + 1
        update["stop_reason"] = (
            STOP_VALID_PACKAGE if update.get("package_valid") else STOP_INVALID_FINAL
        )
        if state.get("current_gap") is not None:
            update["final_note"] = CEILING_NOTE
        return update

    def invalid(state: AgentState) -> dict[str, Any]:
        """Terminate without a package, keeping the reason and the errors."""
        if state.get("stop_reason") == STOP_BUDGET_EXHAUSTED:
            return {}
        return {"stop_reason": STOP_INVALID_INITIAL}

    builder = StateGraph(AgentState, input_schema=AgentInput)
    builder.add_node("parse_round", parse_round)
    builder.add_node("generate_initial", generate_initial)
    builder.add_node("observe", observe)
    builder.add_node("ask", ask)
    builder.add_node("assess_and_admit", assess_and_admit)
    builder.add_node("generate_final", generate_final)
    builder.add_node("invalid", invalid)

    builder.add_edge(START, "parse_round")
    builder.add_edge("parse_round", "generate_initial")
    builder.add_edge("generate_initial", "observe")
    builder.add_conditional_edges(
        "observe",
        route_after_observation,
        {
            "ask": "ask",
            "generate_final": "generate_final",
            "invalid": "invalid",
        },
    )
    builder.add_edge("ask", "assess_and_admit")
    builder.add_edge("assess_and_admit", "observe")
    builder.add_edge("generate_final", END)
    builder.add_edge("invalid", END)
    return builder.compile(checkpointer=checkpointer)


AskCallback = Callable[[str, str], str]


def run_agent(
    job_description: str,
    evidence_source: str,
    evidence_format: str,
    ask_callback: AskCallback,
    settings=None,
    output_dir: Path | None = None,
    model: StructuredModel | None = None,
    extractor: Extractor = extract_requirements,
    matcher: Matcher | None = None,
    round_text: str = "",
    research_text: str = "",
    search: Any = None,
    thread_id: str = "agent",
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[AgentState, list[dict[str, Any]]]:
    """Run the loop to termination, answering interrupts via the callback.

    The trace is assembled from streamed node updates rather than stored in
    state: the parsed round or its absence, every queue selection, every
    interrupt payload, every assessment verdict with its decision reason,
    both generation events, and the stop reason, in order.

    Args:
        job_description: Raw posting text.
        evidence_source: Raw evidence text, corpus or resume.
        evidence_format: ``"markdown"`` or ``"corpus"``.
        ask_callback: Called with (requirement_id, question); returns the
            human's answer.
        settings: Pipeline settings; packaged defaults are used if omitted.
        output_dir: Where to write artifacts, including ``agent_trace.json``
            and ``clarification_records.json``.
        model: Provider for every model stage.
        extractor: Stage 1 implementation for the inner workflow.
        matcher: Stage 2 implementation for the inner workflow.
        round_text: Optional freeform description of the upcoming round.
        thread_id: Checkpoint thread identity for interrupt and resume.
        on_event: Optional observer called with each trace entry as it is
            recorded. Purely additive — the trace and the return value are
            identical with or without it.

    Returns:
        The final state and the ordered trace.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from .config import load_settings
    from .workflow.pipeline import _write_prep_artifacts

    settings = settings or load_settings()
    graph = build_agent_graph(
        model=model,
        checkpointer=InMemorySaver(),
        extractor=extractor,
        matcher=matcher,
        search=search,
        max_agent_actions=settings.max_agent_actions,
        agent_action_cap=settings.agent_action_cap,
        max_questions_per_run=settings.max_questions_per_run,
        min_clarification_length=settings.min_clarification_length,
        max_search_queries=settings.max_search_queries,
        max_research_findings=settings.max_research_findings,
        match_threshold=settings.match_threshold,
        max_matches=settings.max_matches_per_requirement,
        min_requirements=settings.min_requirements,
        max_requirements=settings.max_requirements,
    )
    config = {"configurable": {"thread_id": thread_id}}

    trace: list[dict[str, Any]] = []

    def append(entry: dict[str, Any]) -> None:
        trace.append(entry)
        if on_event is not None:
            on_event(entry)

    def record(event: dict[str, Any]) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for node, update in event.items():
            if node == "parse_round":
                parsed = update.get("round_context")
                append(
                    {
                        "node": node,
                        "round": parsed.model_dump(mode="json", exclude_none=True)
                        if parsed is not None
                        else None,
                    }
                )
            elif node == "observe":
                current = update.get("current_gap")
                append(
                    {
                        "node": node,
                        "selected": current.id if current is not None else None,
                        "question_budget_left": update.get("question_budget_left"),
                        **(
                            {"stop_reason": update["stop_reason"]}
                            if update.get("stop_reason")
                            else {}
                        ),
                    }
                )
            elif node == "__interrupt__":
                pending.extend(item.value for item in update)
                append({"node": "ask", "interrupt": [item.value for item in update]})
            elif node == "assess_and_admit":
                entry: dict[str, Any] = {"node": node}
                records = update.get("clarification_records") or []
                if records:
                    entry["record"] = records[0].model_dump(mode="json", exclude_none=True)
                append(entry)
            elif node in ("generate_initial", "generate_final"):
                entry = {
                    "node": node,
                    "package_valid": update.get("package_valid"),
                }
                if update.get("final_note"):
                    entry["note"] = update["final_note"]
                if not update.get("package_valid") and update.get("validation_errors"):
                    entry["errors"] = update["validation_errors"]
                append(entry)
            elif node == "invalid":
                append({"node": node})
        return pending

    stream_input: Any = {
        "job_description": job_description,
        "evidence_source": evidence_source,
        "evidence_format": evidence_format,
        "round_text": round_text,
        "research_text": research_text,
    }
    while True:
        pending: list[dict[str, Any]] = []
        for event in graph.stream(stream_input, config, stream_mode="updates"):
            pending.extend(record(event))
        if not pending:
            break
        payload = pending[0]
        answer = ask_callback(payload["requirement_id"], payload["question"])
        stream_input = Command(resume=answer)

    state: AgentState = graph.get_state(config).values
    append({"node": "stop", "stop_reason": state.get("stop_reason")})

    if output_dir is not None and settings.write_stage_artifacts:
        output_dir = Path(output_dir)
        _write_prep_artifacts(output_dir, state)
        with open(output_dir / "agent_trace.json", "w", encoding="utf-8") as handle:
            json.dump(trace, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        with open(output_dir / "clarification_records.json", "w", encoding="utf-8") as handle:
            json.dump(
                [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in state.get("clarification_records", [])
                ],
                handle,
                indent=2,
                ensure_ascii=False,
            )
            handle.write("\n")

    return state, trace


# Module-level compiled graph for local graph tooling; model stages resolve a
# provider only when they run.
agent_graph = build_agent_graph()

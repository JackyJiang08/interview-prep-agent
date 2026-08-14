"""The bounded decision loop around the preparation workflow.

    START -> observe -> decide -> authorize
                                    |- generate -> observe
                                    |- ask      -> observe
                                    |- retry    -> decide
                                    |- finish   -> END
                                    |- invalid  -> END

This is the one place in the system where control passes to a model, and the
claim about how little control that is can be stated precisely. Every branch
target is fixed when the graph is built. ``observe`` derives a factual
snapshot and the allowed actions in pure code. ``decide`` shows the model that
snapshot — never hidden reasoning, never raw state — and receives exactly one
proposed action against a schema. ``authorize`` applies every gate in code and
computes the route; the conditional edge maps only that code-chosen value. The
capabilities execute, the budget counts down, and code stops the run. The
model's entire authority is one proposal per cycle; it never routes, never
executes, and never approves its own proposal.

Clarifications gathered at interrupts become first-class ``CL-`` evidence
items, and regeneration passes the enlarged corpus through the unchanged
workflow — so the traceability guarantee extends through the human in the
loop rather than around them.
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
    AgentAction,
    AgentDecision,
    AgentObservation,
    Clarification,
    CoverageLevel,
    EvidenceItem,
    FocusArea,
    HighPriorityGap,
    InterviewStrategy,
    MockQuestion,
    PrepPackage,
    Requirement,
    RequirementMatch,
)
from .providers import ProviderError, StructuredModel
from .workflow.extract import extract_requirements
from .workflow.graph import Extractor, Matcher, build_prep_workflow

DEFAULT_GOAL = "Produce a grounded, validated preparation package without inventing evidence."

MAX_DECISION_RETRIES = 1

# Importance at or above which a gap justifies interrupting a human.
HIGH_PRIORITY_IMPORTANCE = 4

STOP_VALID_PACKAGE = "valid_package_complete"
STOP_INVALID_DECISION = "invalid_decision"
STOP_BUDGET_EXHAUSTED = "action_budget_exhausted"

# Business fields copied back from a workflow run. Nothing else crosses:
# the workflow's own control fields stay its own.
WORKFLOW_RESULT_FIELDS = (
    "evidence",
    "requirements",
    "matches",
    "focus_areas",
    "strategy",
    "mock_questions",
    "prep_package",
    "validation_errors",
    "package_valid",
)

AGENT_INSTRUCTIONS = """\
You propose the next action for a bounded interview-preparation loop.

The runtime has already derived allowed_actions in code, and it will reject
anything else. Choose exactly one action from allowed_actions.

- ASK_USER: pick one requirement from high_priority_gaps whose identifier is
  not in asked_requirement_ids, and phrase one focused, factual question that
  its text and explanation justify. Supply that target_requirement_id and the
  question. Ask for facts the candidate would know, never for reassurance.
- GENERATE_PREP_PACKAGE or FINISH: omit target_requirement_id and question.

Respect steps_remaining. Keep reason_summary to one sentence of fact, not
narration. Return nothing except data conforming to the supplied schema.
"""


class AgentState(TypedDict, total=False):
    """Workflow business state plus the loop's control fields.

    The two clarification lists carry additive reducers: an interrupt node
    restarts on resume, and additive updates are what make that restart safe.
    """

    # source inputs
    job_description: str
    evidence_source: str
    evidence_format: str
    goal: str
    # human-supplied evidence, additive
    clarifications: Annotated[list[Clarification], operator.add]
    clarification_evidence: Annotated[list[EvidenceItem], operator.add]
    asked_requirement_ids: Annotated[list[str], operator.add]
    # workflow-derived business state
    evidence: list[EvidenceItem]
    requirements: list[Requirement]
    matches: list[RequirementMatch]
    focus_areas: list[FocusArea]
    strategy: InterviewStrategy | None
    mock_questions: list[MockQuestion]
    prep_package: PrepPackage | None
    validation_errors: list[str]
    package_valid: bool
    # loop control
    observation: AgentObservation
    decision: AgentDecision
    package_generated: bool
    last_action: AgentAction | None
    action_count: int
    decision_retry_count: int
    authorization_error: str | None
    authorized_route: str
    stop_reason: str | None


class AgentInput(TypedDict):
    """Values the caller supplies when the loop starts."""

    job_description: str
    evidence_source: str
    evidence_format: str


def derive_observation(
    state: AgentState, max_agent_actions: int, max_questions_per_run: int
) -> AgentObservation:
    """Compress business state into the factual snapshot the model is shown.

    Pure code, no model. High-priority gaps are verdicts at GAP coverage whose
    requirement carries importance at or above the threshold, sorted by
    importance descending then identifier; a requirement without importance
    never qualifies, because interrupting a human on a guess is not a
    judgment this code is entitled to make.
    """
    requirements = {item.id: item for item in state.get("requirements", [])}

    gaps: list[HighPriorityGap] = []
    for verdict in state.get("matches", []):
        requirement = requirements.get(verdict.requirement_id)
        if (
            verdict.coverage is CoverageLevel.GAP
            and requirement is not None
            and requirement.importance is not None
            and requirement.importance >= HIGH_PRIORITY_IMPORTANCE
        ):
            gaps.append(
                HighPriorityGap(
                    requirement_id=requirement.id,
                    text=requirement.text,
                    importance=requirement.importance,
                    explanation=verdict.explanation or "No explanation recorded.",
                )
            )
    gaps.sort(key=lambda gap: (-gap.importance, gap.requirement_id))
    gap_ids = [gap.requirement_id for gap in gaps]

    clarifications = state.get("clarifications", [])
    asked = state.get("asked_requirement_ids", [])
    unasked_gap_ids = [identifier for identifier in gap_ids if identifier not in asked]
    steps_remaining = max(0, max_agent_actions - state.get("action_count", 0))
    package_generated = state.get("package_generated", False)
    package_valid = state.get("package_valid", False)
    last_action = state.get("last_action")

    # The allowed set is derived, not suggested. Order of the rules matters:
    # nothing exists yet -> generate; a fresh answer is in hand -> fold it in;
    # an eligible unasked gap and question budget -> ask; a valid package and
    # nothing left to ask -> finish; anything else -> regenerate.
    allowed: list[AgentAction]
    if steps_remaining == 0:
        allowed = []
    elif not package_generated:
        allowed = [AgentAction.GENERATE_PREP_PACKAGE]
    elif last_action is AgentAction.ASK_USER and clarifications:
        allowed = [AgentAction.GENERATE_PREP_PACKAGE]
    elif unasked_gap_ids and len(asked) < max_questions_per_run:
        allowed = [AgentAction.ASK_USER]
    elif package_valid:
        allowed = [AgentAction.FINISH]
    else:
        allowed = [AgentAction.GENERATE_PREP_PACKAGE]

    return AgentObservation(
        package_generated=package_generated,
        package_valid=package_valid,
        high_priority_gap_ids=gap_ids,
        high_priority_gaps=gaps,
        asked_requirement_ids=asked,
        allowed_actions=allowed,
        latest_clarification=clarifications[-1].answer if clarifications else None,
        last_action=last_action,
        steps_remaining=steps_remaining,
    )


def build_decision_prompt(
    goal: str, observation: AgentObservation, previous_error: str | None = None
) -> str:
    """Place the goal and snapshot after the instructions.

    A prior authorization error is included verbatim, so a retry is a
    correction rather than a blind second attempt.
    """
    error_block = (
        f"\n----- PRIOR PROPOSAL REJECTED BY CODE -----\n{previous_error}\n"
        if previous_error
        else ""
    )
    return (
        f"{AGENT_INSTRUCTIONS}\n"
        "----- GOAL -----\n"
        f"{goal}\n"
        "----- OBSERVATION -----\n"
        f"{json.dumps(observation.model_dump(mode='json'), indent=2, ensure_ascii=False)}\n"
        f"{error_block}"
    )


def authorize(
    decision: AgentDecision,
    observation: AgentObservation,
    max_questions_per_run: int,
) -> tuple[Literal["generate", "ask", "finish"], None] | tuple[Literal["invalid"], str]:
    """Apply every code-owned gate to one proposed action.

    Pure function: the proposal and the snapshot in, a route or a rejection
    out. Nothing here consults a model, and nothing outside this function
    decides what a proposal is allowed to do.
    """
    action = decision.next_action

    if observation.steps_remaining < 1:
        return "invalid", (
            f"authorization: the action budget is exhausted "
            f"({len(observation.asked_requirement_ids)} asked, 0 steps remaining)"
        )

    if action not in observation.allowed_actions:
        allowed = ", ".join(item.value for item in observation.allowed_actions) or "none"
        return "invalid", (f"authorization: {action.value} is not in the allowed set ({allowed})")

    if action is AgentAction.GENERATE_PREP_PACKAGE:
        return "generate", None

    if action is AgentAction.FINISH:
        if not observation.package_valid:
            return "invalid", "authorization: FINISH requires a valid package"
        unasked = set(observation.high_priority_gap_ids) - set(observation.asked_requirement_ids)
        if unasked and len(observation.asked_requirement_ids) < max_questions_per_run:
            return "invalid", (
                "authorization: FINISH requires no eligible unasked "
                f"high-priority gap (open: {', '.join(sorted(unasked))})"
            )
        return "finish", None

    # ASK_USER
    if not decision.target_requirement_id or not decision.question:
        return "invalid", ("authorization: ASK_USER requires a target requirement and a question")
    if decision.target_requirement_id not in observation.high_priority_gap_ids:
        return "invalid", (
            f"authorization: {decision.target_requirement_id} is not an eligible high-priority gap"
        )
    if decision.target_requirement_id in observation.asked_requirement_ids:
        return "invalid", (
            f"authorization: {decision.target_requirement_id} has already been asked"
        )
    if len(observation.asked_requirement_ids) >= max_questions_per_run:
        return "invalid", (f"authorization: at most {max_questions_per_run} question(s) per run")
    return "ask", None


def build_agent_graph(
    model: StructuredModel | None = None,
    checkpointer: Any = None,
    extractor: Extractor = extract_requirements,
    matcher: Matcher | None = None,
    max_agent_actions: int = 4,
    max_questions_per_run: int = 1,
    match_threshold: float = 0.30,
    max_matches: int = 3,
    min_requirements: int = 1,
    max_requirements: int = 50,
    min_questions: int = 8,
):
    """Compile the decision loop.

    Args:
        model: Provider for the decide stage and the workflow's model stages.
            Resolved lazily when omitted, so the graph compiles offline.
        checkpointer: Optional checkpointer; required for interrupt and
            resume, since a resumed thread is the same thread.
        extractor: Stage 1 implementation for the inner workflow.
        matcher: Stage 2 implementation for the inner workflow.
        max_agent_actions: Hard ceiling on actions per run.
        max_questions_per_run: Hard ceiling on human interrupts per run.
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
        match_threshold=match_threshold,
        max_matches=max_matches,
        min_requirements=min_requirements,
        max_requirements=max_requirements,
        min_questions=min_questions,
    )

    def observe(state: AgentState) -> dict[str, Any]:
        return {
            "goal": state.get("goal") or DEFAULT_GOAL,
            "observation": derive_observation(state, max_agent_actions, max_questions_per_run),
            "decision_retry_count": 0,
        }

    def decide(state: AgentState) -> dict[str, Any]:
        prompt = build_decision_prompt(
            state.get("goal") or DEFAULT_GOAL,
            state["observation"],
            previous_error=state.get("authorization_error"),
        )
        payload = resolve_model().generate_json(prompt, AgentDecision.model_json_schema())
        try:
            decision = AgentDecision.model_validate(payload, from_attributes=True)
        except Exception as error:  # noqa: BLE001 - pydantic raises several types
            raise ProviderError(
                f"model response did not match the requested schema: {error}"
            ) from error
        # Only the validated decision enters state, never the raw response.
        return {"decision": decision}

    def authorize_node(state: AgentState) -> dict[str, Any]:
        route, error = authorize(state["decision"], state["observation"], max_questions_per_run)
        if route != "invalid":
            return {
                "authorized_route": route,
                "authorization_error": None,
                "last_action": state["decision"].next_action,
                "action_count": state.get("action_count", 0) + 1,
                **({"stop_reason": STOP_VALID_PACKAGE} if route == "finish" else {}),
            }

        budget_spent = state["observation"].steps_remaining < 1
        retries = state.get("decision_retry_count", 0)
        if not budget_spent and retries < MAX_DECISION_RETRIES:
            # A retry can fix a bad proposal; it cannot fix an empty budget.
            return {
                "authorized_route": "retry",
                "authorization_error": error,
                "decision_retry_count": retries + 1,
            }
        return {
            "authorized_route": "invalid",
            "authorization_error": error,
            "stop_reason": STOP_BUDGET_EXHAUSTED if budget_spent else STOP_INVALID_DECISION,
        }

    def route_authorized(
        state: AgentState,
    ) -> Literal["generate", "ask", "finish", "retry", "invalid"]:
        """Return only the route authorization already computed."""
        return state["authorized_route"]

    def generate(state: AgentState) -> dict[str, Any]:
        """Run the unchanged workflow over the corpus plus clarifications.

        The enlarged corpus is serialized back to the canonical YAML form, so
        the workflow's own boundary parses it exactly as it parses any corpus
        — clarification items included, their identifiers intact.
        """
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
            }
        )
        update = {field: result.get(field) for field in WORKFLOW_RESULT_FIELDS}
        update["package_generated"] = True
        return update

    def ask(state: AgentState) -> dict[str, Any]:
        """Interrupt for one factual answer and fold it in as evidence.

        Everything before ``interrupt()`` must stay idempotent: the node
        restarts from its top on resume, and only the additive updates
        returned after the answer arrives may change state.
        """
        decision = state["decision"]
        if decision.target_requirement_id is None or decision.question is None:
            raise ValueError("an authorized ASK_USER decision carries a target and a question")

        answer = interrupt(
            {
                "type": "evidence_request",
                "requirement_id": decision.target_requirement_id,
                "question": decision.question,
            }
        )
        clarification = Clarification(
            requirement_id=decision.target_requirement_id,
            question=decision.question,
            answer=str(answer),
        )
        minted = clarification_to_evidence(clarification, len(state.get("clarifications", [])) + 1)
        return {
            "clarifications": [clarification],
            "clarification_evidence": [minted],
            "asked_requirement_ids": [decision.target_requirement_id],
        }

    def finish(_state: AgentState) -> dict[str, Any]:
        """End after code has authorized FINISH."""
        return {}

    def invalid(_state: AgentState) -> dict[str, Any]:
        """End without executing anything after a rejected proposal."""
        return {}

    builder = StateGraph(AgentState, input_schema=AgentInput)
    builder.add_node("observe", observe)
    builder.add_node("decide", decide)
    builder.add_node("authorize", authorize_node)
    builder.add_node("generate", generate)
    builder.add_node("ask", ask)
    builder.add_node("finish", finish)
    builder.add_node("invalid", invalid)

    builder.add_edge(START, "observe")
    builder.add_edge("observe", "decide")
    builder.add_edge("decide", "authorize")
    builder.add_conditional_edges(
        "authorize",
        route_authorized,
        {
            "generate": "generate",
            "ask": "ask",
            "finish": "finish",
            "retry": "decide",
            "invalid": "invalid",
        },
    )
    builder.add_edge("generate", "observe")
    builder.add_edge("ask", "observe")
    builder.add_edge("finish", END)
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
    thread_id: str = "agent",
) -> tuple[AgentState, list[dict[str, Any]]]:
    """Run the loop to termination, answering interrupts via the callback.

    The trace is assembled from the streamed node updates rather than stored
    in state, which keeps state business-and-control data only while still
    leaving the decision loop the same quality of record the workflow stages
    leave: every observation, every proposal, every authorization verdict,
    and the stop reason, in order.

    Args:
        job_description: Raw posting text.
        evidence_source: Raw evidence text, corpus or resume.
        evidence_format: ``"markdown"`` or ``"corpus"``.
        ask_callback: Called with (requirement_id, question); returns the
            human's answer.
        settings: Pipeline settings; packaged defaults are used if omitted.
        output_dir: Where to write artifacts, including ``agent_trace.json``.
        model: Provider for every model stage.
        extractor: Stage 1 implementation for the inner workflow.
        matcher: Stage 2 implementation for the inner workflow.
        thread_id: Checkpoint thread identity for interrupt and resume.

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
        max_agent_actions=settings.max_agent_actions,
        max_questions_per_run=settings.max_questions_per_run,
        match_threshold=settings.match_threshold,
        max_matches=settings.max_matches_per_requirement,
        min_requirements=settings.min_requirements,
        max_requirements=settings.max_requirements,
    )
    config = {"configurable": {"thread_id": thread_id}}

    trace: list[dict[str, Any]] = []

    def record(event: dict[str, Any]) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for node, update in event.items():
            if node == "observe":
                trace.append(
                    {
                        "node": node,
                        "observation": update["observation"].model_dump(mode="json"),
                    }
                )
            elif node == "decide":
                trace.append(
                    {
                        "node": node,
                        "decision": update["decision"].model_dump(mode="json", exclude_none=True),
                    }
                )
            elif node == "authorize":
                trace.append(
                    {
                        "node": node,
                        "route": update.get("authorized_route"),
                        "error": update.get("authorization_error"),
                        **(
                            {"stop_reason": update["stop_reason"]}
                            if update.get("stop_reason")
                            else {}
                        ),
                    }
                )
            elif node == "__interrupt__":
                pending.extend(item.value for item in update)
                trace.append({"node": "ask", "interrupt": [item.value for item in update]})
            elif node in ("generate", "ask", "finish", "invalid"):
                trace.append({"node": node})
        return pending

    stream_input: Any = {
        "job_description": job_description,
        "evidence_source": evidence_source,
        "evidence_format": evidence_format,
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
    trace.append({"node": "stop", "stop_reason": state.get("stop_reason")})

    if output_dir is not None and settings.write_stage_artifacts:
        output_dir = Path(output_dir)
        _write_prep_artifacts(output_dir, state)
        with open(output_dir / "agent_trace.json", "w", encoding="utf-8") as handle:
            json.dump(trace, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

    return state, trace


# Module-level compiled graph for local graph tooling; the decide node and the
# workflow's model stages resolve a provider only when they run.
agent_graph = build_agent_graph()

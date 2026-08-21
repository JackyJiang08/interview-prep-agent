"""Drive the real compiled agent graph through one scenario run."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agentevals.graph_trajectory.utils import (
    extract_langgraph_trajectory_from_thread,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command

from ..agent import build_agent_graph
from ..models import CoverageLevel
from ..providers import StructuredModel
from .dataset import scenario_by_id, source_inputs
from .runtime import CountingProvider, FixtureProvider

# Model types the checkpointer may serialize; explicit registration keeps
# checkpoint round-trips exact and forward-compatible.
CHECKPOINT_ALLOWED_TYPES = [
    ("interview_prep_agent.models", type_name)
    for type_name in (
        "Clarification",
        "ClarificationAssessment",
        "ClarificationRecord",
        "Coverage",
        "CoverageLevel",
        "EvidenceItem",
        "EvidenceMatch",
        "FocusArea",
        "FocusPlan",
        "InterviewRound",
        "InterviewStrategy",
        "MockQuestion",
        "PlanItem",
        "PrepPackage",
        "Requirement",
        "RequirementMatch",
        "Status",
    )
]


def _checkpointer() -> InMemorySaver:
    return InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_ALLOWED_TYPES))


def _run_thread(
    *,
    profile: str,
    run: dict[str, Any],
    model: StructuredModel,
) -> dict[str, Any]:
    """Run one thread to termination, draining interrupts from the script."""
    compiled = build_agent_graph(model=model, checkpointer=_checkpointer())
    config = {"configurable": {"thread_id": f"behavior-{uuid4()}"}}
    inputs = {**source_inputs(profile), "round_text": run["round_text"]}

    state = compiled.invoke(inputs, config=config)
    interrupt_count = 0
    while state.get("__interrupt__"):
        payload = state["__interrupt__"][0].value
        requirement_id = payload["requirement_id"]
        answers = run["answers_by_requirement"]
        if requirement_id not in answers:
            raise ValueError(f"{run['run_id']} has no scripted answer for {requirement_id}")
        interrupt_count += 1
        state = compiled.invoke(Command(resume=answers[requirement_id]), config=config)

    extracted = extract_langgraph_trajectory_from_thread(compiled, config)
    records = state.get("clarification_records", [])
    clarifications = state.get("clarifications", [])
    verdicts = state.get("matches", [])
    strategy = state.get("strategy")
    questions = state.get("mock_questions", [])
    return {
        "steps": extracted["outputs"]["steps"],
        "interrupt_count": interrupt_count,
        "processed_ids": list(state.get("processed_requirement_ids", [])),
        "accepted_ids": [item.requirement_id for item in clarifications],
        "rejected_ids": [record.requirement_id for record in records if not record.accepted],
        "remaining_gap_ids": [
            verdict.requirement_id for verdict in verdicts if verdict.coverage is CoverageLevel.GAP
        ],
        "package_valid": state.get("package_valid", False),
        "stop_reason": state.get("stop_reason"),
        "audit_records": [
            {
                "requirement_id": record.requirement_id,
                "assessment_target_id": record.assessment.target_requirement_id,
                "accepted": record.accepted,
            }
            for record in records
        ],
        "evidence_signature": [
            item.model_dump(mode="json", exclude_none=True) for item in state.get("evidence", [])
        ],
        "coverage_signature": [
            {
                "requirement_id": verdict.requirement_id,
                "coverage": verdict.coverage.value if verdict.coverage else None,
                "evidence_ids": [match.evidence_id for match in verdict.matches],
            }
            for verdict in verdicts
        ],
        "guidance_signature": {
            "positioning_statement": (
                strategy.positioning_statement if strategy is not None else None
            ),
            "questions": [question.question for question in questions],
        },
    }


def run_scenario(inputs: dict[str, Any], *, suite: str) -> dict[str, Any]:
    """Run one dataset scenario with fixture or live model dependencies."""
    scenario = scenario_by_id(inputs["scenario_id"])
    scripted = {run["run_id"]: run for run in scenario["runs"]}
    profile = inputs["profile"]

    results: dict[str, Any] = {}
    model_backed_runs: list[bool] = []
    for run in inputs["runs"]:
        if suite == "offline":
            model: StructuredModel = FixtureProvider(
                scripted[run["run_id"]].get("assessments_by_requirement", {})
            )
            result = _run_thread(profile=profile, run=run, model=model)
            result["model_backed"] = False
            result["model_call_count"] = 0
        elif suite == "live":
            from ..providers import build_model

            counting = CountingProvider(build_model())
            result = _run_thread(profile=profile, run=run, model=counting)
            result["model_backed"] = counting.call_count > 0
            result["model_call_count"] = counting.call_count
        else:
            raise ValueError(f"unknown suite {suite!r}")
        model_backed_runs.append(result["model_backed"])
        results[run["run_id"]] = result

    return {
        "scenario_id": inputs["scenario_id"],
        "suite": suite,
        "model_backed": suite == "live" and all(model_backed_runs),
        "runs": results,
    }


def make_target(suite: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Create the target callable handed to the experiment runner."""

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        return run_scenario(inputs, suite=suite)

    target.__name__ = f"{suite}_suite"
    return target

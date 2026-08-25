"""Behavioral evaluators scoring outcome, state, and trajectory.

These freeze behavior; none of them measures output quality. A green matrix
means the agent still does what it did, not that what it does is good — the
latter claim belongs to the labelled evaluation set, which this is not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentevals.graph_trajectory.strict import graph_trajectory_strict_match

Evaluator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _expected_runs(reference_outputs: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs["runs"]


def trajectory_match(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """Every interrupt-and-resume turn follows the frozen node order."""
    scores = []
    for run_id, expected in _expected_runs(reference_outputs).items():
        result = graph_trajectory_strict_match(
            outputs={"steps": outputs["runs"][run_id]["steps"], "results": []},
            reference_outputs={"steps": expected["expected_steps"], "results": []},
        )
        scores.append(bool(result["score"]))
    return {"key": "graph_trajectory_strict_match", "score": all(scores)}


def all_gaps_processed(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    """Processed identifiers and interrupt counts match, run by run."""
    score = all(
        outputs["runs"][run_id]["processed_ids"] == expected["expected_processed_ids"]
        and outputs["runs"][run_id]["interrupt_count"] == expected["expected_interrupt_count"]
        for run_id, expected in _expected_runs(reference_outputs).items()
    )
    return {"key": "all_gaps_processed", "score": score}


def admission_set_correct(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    """Accepted, rejected and remaining-gap sets match; audit is complete."""
    scores = []
    for run_id, expected in _expected_runs(reference_outputs).items():
        actual = outputs["runs"][run_id]
        audited = [record["requirement_id"] for record in actual["audit_records"]]
        rejected_isolated = not (set(actual["rejected_ids"]) & set(actual["accepted_ids"]))
        scores.append(
            actual["accepted_ids"] == expected["expected_accepted_ids"]
            and actual["rejected_ids"] == expected["expected_rejected_ids"]
            and actual["remaining_gap_ids"] == expected["expected_remaining_gap_ids"]
            and audited == expected["expected_processed_ids"]
            and rejected_isolated
        )
    return {"key": "admission_set_correct", "score": all(scores)}


def terminal_state_valid(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    """The final package gate outcome and stop reason match."""
    score = all(
        outputs["runs"][run_id]["package_valid"] == expected["expected_package_valid"]
        and outputs["runs"][run_id]["stop_reason"] == expected["expected_stop_reason"]
        for run_id, expected in _expected_runs(reference_outputs).items()
    )
    return {"key": "terminal_state_valid", "score": score}


def round_guidance_changed(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    """Round context changed guidance while evidence and coverage held still.

    Null-safe: a scenario that declares no expectation passes trivially, so
    the evaluator can run on every scenario without special-casing.
    """
    expected = reference_outputs.get("round_guidance_changed")
    if expected is None:
        return {
            "key": "round_guidance_changed",
            "score": True,
            "comment": "not applicable to this scenario",
        }
    runs = list(outputs["runs"].values())
    observed = (
        len(runs) == 2
        and runs[0]["evidence_signature"] == runs[1]["evidence_signature"]
        and runs[0]["coverage_signature"] == runs[1]["coverage_signature"]
        and runs[0]["guidance_signature"] != runs[1]["guidance_signature"]
    )
    return {"key": "round_guidance_changed", "score": observed == expected}


def research_grounded(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """Findings were minted and every preparation citation resolves.

    Null-safe: scenarios that declare no expectation pass trivially. Where
    declared, every run must mint sequential findings, cite at least one, and
    cite nothing unminted — while candidate evidence stays untouched, which
    the admission and coverage evaluators already hold constant.
    """
    expected = reference_outputs.get("research_grounded")
    if expected is None:
        return {
            "key": "research_grounded",
            "score": True,
            "comment": "not applicable to this scenario",
        }
    scores = []
    for run in outputs["runs"].values():
        signature = run.get("research_signature", {})
        finding_ids = signature.get("finding_ids", [])
        cited = signature.get("cited_ids", [])
        sequential = finding_ids == [f"SRC-{index:03d}" for index in range(1, len(finding_ids) + 1)]
        scores.append(
            len(finding_ids) > 0
            and sequential
            and len(cited) > 0
            and set(cited) <= set(finding_ids)
        )
    return {"key": "research_grounded", "score": all(scores) == expected}


def model_backed(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """The live suite made genuine provider calls on every run."""
    del reference_outputs
    score = outputs.get("model_backed") is True and all(
        run["model_backed"] is True and run["model_call_count"] > 0
        for run in outputs["runs"].values()
    )
    return {"key": "model_backed", "score": score}


def evaluators_for_suite(suite: str) -> list[Evaluator]:
    """Return the evaluator set for a named suite."""
    evaluators: list[Evaluator] = [
        trajectory_match,
        all_gaps_processed,
        admission_set_correct,
        terminal_state_valid,
        round_guidance_changed,
        research_grounded,
    ]
    if suite == "live":
        evaluators.append(model_backed)
    return evaluators


def evaluate_locally(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
    *,
    suite: str,
) -> dict[str, bool]:
    """Apply the suite's evaluators without any experiment upload."""
    return {
        result["key"]: bool(result["score"])
        for evaluator in evaluators_for_suite(suite)
        for result in [evaluator(outputs, reference_outputs)]
    }

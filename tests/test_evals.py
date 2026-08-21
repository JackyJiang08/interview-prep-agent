"""Contract tests for the behavioral regression framework itself."""

from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from interview_prep_agent.evals import dataset as dataset_module
from interview_prep_agent.evals.dataset import (
    dataset_example,
    load_dataset,
    scenario_by_id,
    scenarios_for_suite,
    source_inputs,
)
from interview_prep_agent.evals.evaluators import (
    admission_set_correct,
    evaluate_locally,
    round_guidance_changed,
    terminal_state_valid,
)
from interview_prep_agent.evals.runner import run_local
from interview_prep_agent.evals.target import run_scenario


def _mutated_dataset(mutate):
    payload = deepcopy(load_dataset())
    mutate(payload)
    return payload


def _expect_invalid(payload, match: str):
    with patch.object(dataset_module, "_package_text", return_value=json.dumps(payload)):
        with pytest.raises(ValueError, match=match):
            load_dataset()


# --- dataset validation -------------------------------------------------------


def test_the_committed_dataset_validates():
    payload = load_dataset()
    assert payload["dataset_name"] == "interview-prep-agent-behavior"
    assert len(payload["scenarios"]) == 5


def test_duplicate_scenario_ids_are_rejected():
    def mutate(payload):
        payload["scenarios"].append(deepcopy(payload["scenarios"][0]))

    _expect_invalid(_mutated_dataset(mutate), "identifiers must be unique")


def test_an_unknown_suite_is_rejected():
    def mutate(payload):
        payload["scenarios"][0]["suites"] = ["offline", "nightly"]

    _expect_invalid(_mutated_dataset(mutate), "unsupported suites")


def test_inconsistent_run_references_are_rejected():
    def mutate(payload):
        payload["scenarios"][0]["reference"]["runs"]["phantom"] = deepcopy(
            next(iter(payload["scenarios"][0]["reference"]["runs"].values()))
        )

    _expect_invalid(_mutated_dataset(mutate), "run references are inconsistent")


def test_an_unknown_trajectory_template_is_rejected():
    def mutate(payload):
        runs = payload["scenarios"][0]["reference"]["runs"]
        next(iter(runs.values()))["expected_trajectory"] = "missing-template"

    _expect_invalid(_mutated_dataset(mutate), "unknown trajectory")


def test_unknown_suite_and_profile_lookups_raise():
    with pytest.raises(ValueError, match="unknown suite"):
        scenarios_for_suite("nightly")
    with pytest.raises(ValueError, match="unknown profile"):
        source_inputs("partial")


def test_the_live_suite_excludes_the_offline_only_scenario():
    live_ids = {item["scenario_id"] for item in scenarios_for_suite("live")}
    assert "wrong-target-assessment" not in live_ids
    offline_ids = {item["scenario_id"] for item in scenarios_for_suite("offline")}
    assert "wrong-target-assessment" in offline_ids


# --- evaluator scoring on hand-built payloads ---------------------------------


def _run_payload(**updates):
    payload = {
        "steps": [["__start__"]],
        "interrupt_count": 0,
        "processed_ids": [],
        "accepted_ids": [],
        "rejected_ids": [],
        "remaining_gap_ids": [],
        "package_valid": True,
        "stop_reason": "valid_package_complete",
        "audit_records": [],
        "evidence_signature": [{"id": "EV-001"}],
        "coverage_signature": [{"requirement_id": "REQ-001"}],
        "guidance_signature": {"positioning_statement": "a", "questions": []},
    }
    payload.update(updates)
    return payload


def _reference(**updates):
    expected = {
        "expected_steps": [["__start__"]],
        "expected_interrupt_count": 0,
        "expected_processed_ids": [],
        "expected_accepted_ids": [],
        "expected_rejected_ids": [],
        "expected_remaining_gap_ids": [],
        "expected_package_valid": True,
        "expected_stop_reason": "valid_package_complete",
    }
    expected.update(updates)
    return {"runs": {"only": expected}}


def test_admission_set_mismatch_scores_red():
    outputs = {"runs": {"only": _run_payload(accepted_ids=["REQ-009"])}}
    assert admission_set_correct(outputs, _reference())["score"] is False


def test_terminal_state_mismatch_scores_red():
    outputs = {"runs": {"only": _run_payload(stop_reason="invalid_final_package")}}
    assert terminal_state_valid(outputs, _reference())["score"] is False


def test_round_guidance_is_null_safe():
    outputs = {"runs": {"only": _run_payload()}}
    result = round_guidance_changed(outputs, _reference())
    assert result["score"] is True
    assert "not applicable" in result["comment"]


def test_round_guidance_detects_unchanged_guidance():
    runs = {"a": _run_payload(), "b": _run_payload()}
    reference = {"round_guidance_changed": True, "runs": {}}
    assert round_guidance_changed({"runs": runs}, reference)["score"] is False


def test_round_guidance_passes_when_only_guidance_differs():
    runs = {
        "a": _run_payload(),
        "b": _run_payload(guidance_signature={"positioning_statement": "b", "questions": []}),
    }
    reference = {"round_guidance_changed": True, "runs": {}}
    assert round_guidance_changed({"runs": runs}, reference)["score"] is True


def test_evaluate_locally_includes_model_backed_only_for_live():
    outputs = {"runs": {"only": _run_payload()}, "model_backed": False}
    offline = evaluate_locally(outputs, _reference(), suite="offline")
    assert "model_backed" not in offline
    live = evaluate_locally(outputs, _reference(), suite="live")
    assert live["model_backed"] is False


# --- offline target end to end ------------------------------------------------


def test_offline_target_drains_interrupts_on_the_mixed_scenario():
    scenario = scenario_by_id("mixed-clarifications")
    example = dataset_example(scenario)

    outputs = run_scenario(example["inputs"], suite="offline")

    run = outputs["runs"]["mixed"]
    assert run["interrupt_count"] == 3
    assert run["processed_ids"] == ["REQ-002", "REQ-005", "REQ-006"]
    assert run["accepted_ids"] == ["REQ-002", "REQ-006"]
    assert run["rejected_ids"] == ["REQ-005"]
    assert run["remaining_gap_ids"] == ["REQ-005"]
    assert run["package_valid"] is True
    assert outputs["model_backed"] is False


def test_the_offline_suite_is_green_on_the_committed_dataset(capsys):
    assert run_local("offline") is True
    printed = capsys.readouterr().out
    assert "graph_trajectory_strict_match" in printed
    assert "FAIL" not in printed

"""Load and validate the behavioral regression dataset.

The dataset freezes *behavior* — trajectories, state deltas, outcomes — for a
set of scenarios, so a future change that silently alters what the agent does
turns a matrix cell red. It deliberately measures nothing about output
quality: a frozen behavior can be a frozen mistake, and only the labelled
evaluation set, which this is not, could say otherwise.
"""

from __future__ import annotations

import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml


def _sample_path(name: str) -> Path:
    """Locate a committed sample input.

    Two layouts must both work: a repository checkout, where the package sits
    under ``src/`` beside ``examples/``, and an installed package, where the
    samples travel beside the working directory instead. Checking both keeps
    the demo suite runnable in a container without duplicating the files into
    package data.
    """
    candidates = (
        Path(__file__).resolve().parents[3] / "examples" / name,
        Path.cwd() / "examples" / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Report the checkout path: it is the one a developer can act on.
    return candidates[0]


JOB_DESCRIPTION_PATH = _sample_path("sample_job_description.txt")
GAPPED_EVIDENCE_PATH = _sample_path("sample_evidence.yaml")

SUITES = {"offline", "live"}


def _package_text(name: str) -> str:
    return (files("interview_prep_agent.evals") / name).read_text(encoding="utf-8")


def load_dataset() -> dict[str, Any]:
    """Return the validated dataset document.

    Validation is structural and strict: a dataset that references a run,
    suite or trajectory that does not exist is a broken contract, not a
    partial one.
    """
    payload = json.loads(_package_text("dataset.json"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("the dataset must contain scenarios")

    scenario_ids = [scenario.get("scenario_id") for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("scenario identifiers must be unique")

    templates = payload.get("trajectory_templates", {})
    for scenario in scenarios:
        identifier = scenario.get("scenario_id")
        declared = set(scenario.get("suites", []))
        if not declared or not declared <= SUITES:
            raise ValueError(f"{identifier} declares unsupported suites")

        runs = scenario.get("runs", [])
        reference_runs = scenario.get("reference", {}).get("runs", {})
        run_ids = [run.get("run_id") for run in runs]
        if len(run_ids) != len(set(run_ids)) or set(run_ids) != set(reference_runs):
            raise ValueError(f"{identifier} run references are inconsistent")

        for expected in reference_runs.values():
            if expected.get("expected_trajectory") not in templates:
                raise ValueError(f"{identifier} references an unknown trajectory")
    return payload


def scenarios_for_suite(suite: str) -> list[dict[str, Any]]:
    """Select the scenarios belonging to one named suite."""
    if suite not in SUITES:
        raise ValueError(f"unknown suite {suite!r}; choose from offline, live")
    return [scenario for scenario in load_dataset()["scenarios"] if suite in scenario["suites"]]


def scenario_by_id(scenario_id: str) -> dict[str, Any]:
    """Resolve one scenario by its stable identifier."""
    for scenario in load_dataset()["scenarios"]:
        if scenario["scenario_id"] == scenario_id:
            return scenario
    raise KeyError(f"unknown scenario {scenario_id!r}")


def source_inputs(profile: str) -> dict[str, str]:
    """Resolve a fixture profile into the repo's own sample inputs.

    ``gapped`` is the committed synthetic corpus, which leaves three gaps
    against the sample posting; ``complete`` is a corpus fixture covering
    every requirement, so a run interrupts for nothing.
    """
    job_description = JOB_DESCRIPTION_PATH.read_text(encoding="utf-8")
    if profile == "gapped":
        evidence_source = GAPPED_EVIDENCE_PATH.read_text(encoding="utf-8")
    elif profile == "complete":
        evidence_source = _package_text("complete_evidence.yaml")
    else:
        raise ValueError(f"unknown profile {profile!r}")
    # Both profiles must parse; failing here beats failing mid-run.
    yaml.safe_load(evidence_source)
    return {
        "job_description": job_description,
        "evidence_source": evidence_source,
        "evidence_format": "corpus",
    }


def dataset_example(scenario: dict[str, Any]) -> dict[str, Any]:
    """Convert one scenario into experiment example inputs and outputs."""
    inputs = {key: scenario[key] for key in ("scenario_id", "description", "profile")}
    inputs["runs"] = [
        {key: run[key] for key in ("run_id", "round_text", "answers_by_requirement")}
        for run in scenario["runs"]
    ]
    reference = deepcopy(scenario["reference"])
    templates = load_dataset()["trajectory_templates"]
    for expected in reference["runs"].values():
        trajectory_name = expected.pop("expected_trajectory")
        expected["expected_steps"] = templates[trajectory_name]
    return {
        "inputs": inputs,
        "outputs": reference,
        "metadata": {"kind": "behavior-regression", "suites": scenario["suites"]},
    }

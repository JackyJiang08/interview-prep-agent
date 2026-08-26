"""Run the behavior suites locally or as a remote experiment.

Local mode constructs no experiment client, needs no credentials and touches
no network: it runs the scenarios, prints the scenario-by-evaluator matrix,
and reports red as a nonzero exit. Remote mode lazily imports the experiment
client, syncs the dataset idempotently under deterministic example
identifiers, runs the experiment and prints its URL.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from .dataset import dataset_example, load_dataset, scenarios_for_suite
from .evaluators import evaluate_locally, evaluators_for_suite
from .target import make_target, run_scenario

OFFLINE_METRICS = (
    "graph_trajectory_strict_match",
    "all_gaps_processed",
    "admission_set_correct",
    "terminal_state_valid",
    "round_guidance_changed",
    "research_grounded",
)


def _example_id(dataset_name: str, suite: str, scenario_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{dataset_name}:{suite}:{scenario_id}")


def print_matrix(rows: list[tuple[str, dict[str, bool]]]) -> bool:
    """Print the scenario-by-evaluator matrix; return whether all passed."""
    metric_names = list(rows[0][1]) if rows else []
    scenario_width = max([len("scenario"), *(len(name) for name, _ in rows)], default=8)
    widths = {name: max(len(name), len("PASS")) for name in metric_names}
    print(
        "scenario".ljust(scenario_width),
        *(name.ljust(widths[name]) for name in metric_names),
        sep="  ",
    )
    all_green = True
    for scenario_id, metrics in rows:
        cells = []
        for name in metric_names:
            passed = metrics[name]
            all_green = all_green and passed
            cells.append(("PASS" if passed else "FAIL").ljust(widths[name]))
        print(scenario_id.ljust(scenario_width), *cells, sep="  ")
    return all_green


def run_local(suite: str, provider: str = "gemini") -> bool:
    """Run one suite in-process and print the matrix."""
    rows = []
    for scenario in scenarios_for_suite(suite):
        example = dataset_example(scenario)
        outputs = run_scenario(example["inputs"], suite=suite, provider=provider)
        metrics = evaluate_locally(outputs, example["outputs"], suite=suite)
        rows.append((scenario["scenario_id"], metrics))
    return print_matrix(rows)


def _require_environment(suite: str, provider: str = "gemini") -> None:
    from ..config import load_settings

    load_settings()  # loads .env so exported credentials are visible
    missing = []
    if not os.getenv("LANGSMITH_API_KEY"):
        missing.append("LANGSMITH_API_KEY")
    if suite == "live":
        if provider == "gemini" and not os.getenv("GEMINI_API_KEY"):
            missing.append("GEMINI_API_KEY")
        if provider == "azure" and not os.getenv("AZURE_OPENAI_API_KEY"):
            missing.append("AZURE_OPENAI_API_KEY")
        if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            missing.append("ANTHROPIC_API_KEY")
    if missing:
        raise RuntimeError("set " + " and ".join(missing) + " before running a remote experiment")
    os.environ.setdefault("LANGSMITH_TRACING", "true")


def _sync_dataset(client: Any, *, suite: str) -> tuple[str, dict[str, UUID]]:
    """Create or update the remote dataset under deterministic example ids."""
    from langsmith.schemas import ExampleCreate, ExampleUpdate

    payload = load_dataset()
    dataset_name = payload["dataset_name"]
    if not client.has_dataset(dataset_name=dataset_name):
        client.create_dataset(
            dataset_name,
            description="Behavioral regression contracts for the agent graph.",
            metadata={"reference_kind": "behavior-contract"},
        )

    examples_by_id: dict[UUID, dict[str, Any]] = {}
    example_ids: dict[str, UUID] = {}
    for scenario in scenarios_for_suite(suite):
        example = dataset_example(scenario)
        stable_id = _example_id(dataset_name, suite, scenario["scenario_id"])
        example_ids[scenario["scenario_id"]] = stable_id
        examples_by_id[stable_id] = example

    existing = {
        item.id
        for item in client.list_examples(dataset_name=dataset_name)
        if item.id in examples_by_id
    }
    creates, updates = [], []
    for stable_id, example in examples_by_id.items():
        kind = ExampleUpdate if stable_id in existing else ExampleCreate
        item = kind(
            id=stable_id,
            inputs=example["inputs"],
            outputs=example["outputs"],
            metadata=example["metadata"],
        )
        (updates if stable_id in existing else creates).append(item)
    if creates:
        client.create_examples(dataset_name=dataset_name, examples=creates)
    if updates:
        client.update_examples(dataset_name=dataset_name, updates=updates)
    return dataset_name, example_ids


def run_remote(suite: str, experiment: str, provider: str = "gemini") -> bool:
    """Sync the dataset, run the experiment, print the matrix and URL."""
    _require_environment(suite, provider)
    from langsmith import Client

    client = Client()
    dataset_name, example_ids = _sync_dataset(client, suite=suite)
    selected = scenarios_for_suite(suite)
    examples = list(
        client.list_examples(
            dataset_name=dataset_name,
            example_ids=[example_ids[item["scenario_id"]] for item in selected],
        )
    )
    results = client.evaluate(
        make_target(suite, provider=provider),
        data=examples,
        evaluators=evaluators_for_suite(suite),
        experiment_prefix=experiment,
        max_concurrency=1,
        metadata={
            "suite": suite,
            "runtime": "live" if suite == "live" else "fixture",
            "provider": provider if suite == "live" else None,
        },
        error_handling="log",
    )

    expected_metrics = (*OFFLINE_METRICS, "model_backed") if suite == "live" else OFFLINE_METRICS
    rows = []
    targets_succeeded = True
    for row in results:
        scenario_id = row["example"].inputs["scenario_id"]
        observed = {
            result.key: bool(result.score) for result in row["evaluation_results"]["results"]
        }
        rows.append((scenario_id, {key: observed.get(key, False) for key in expected_metrics}))
        targets_succeeded = targets_succeeded and row["run"].error is None
    matrix_green = print_matrix(sorted(rows))
    if results.url:
        print(f"experiment: {results.url}")
    return len(rows) == len(selected) and targets_succeeded and matrix_green

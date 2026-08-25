"""Demo inputs and the demo provider.

Demo mode needs no credentials: the graph runs against the same fixture
provider the evaluation suite injects. The committed scenarios are the
selectable demo inputs; a raw-input demo session gets an echo assessor whose
verdict admits any answer the code-owned gates would then bound — the gates,
not the assessor, remain the authority, exactly as in production.
"""

from __future__ import annotations

from typing import Any

from ..evals.dataset import scenario_by_id, scenarios_for_suite, source_inputs
from ..evals.runtime import FixtureProvider


def list_demos() -> list[dict[str, Any]]:
    """The committed scenarios, as selectable demo inputs."""
    demos = []
    for scenario in scenarios_for_suite("offline"):
        run = scenario["runs"][0]
        demos.append(
            {
                "demo_id": scenario["scenario_id"],
                "description": scenario["description"],
                "profile": scenario["profile"],
                "round_text": run["round_text"],
                "suggested_answers": run["answers_by_requirement"],
            }
        )
    return demos


def demo_inputs(demo_id: str) -> dict[str, str]:
    """Resolve a demo id into the create-session input fields."""
    scenario = scenario_by_id(demo_id)
    run = scenario["runs"][0]
    inputs = source_inputs(scenario["profile"])
    return {
        "job_description": inputs["job_description"],
        "evidence_source": inputs["evidence_source"],
        "evidence_format": "yaml",
        "round_text": run["round_text"],
    }


def demo_provider(demo_id: str | None) -> FixtureProvider:
    """The fixture provider for a demo session.

    A scenario-backed session uses the scenario's scripted assessments, so the
    demo reproduces the committed behavior — including rejections. A raw-input
    session uses the echo assessor.
    """
    if demo_id is not None:
        scenario = scenario_by_id(demo_id)
        return FixtureProvider(scenario["runs"][0].get("assessments_by_requirement", {}))
    return EchoAssessorProvider({})


class EchoAssessorProvider(FixtureProvider):
    """Fixture provider whose assessor admits what the gates then bound.

    The verdict is always valid and the admitted claim is the stripped answer
    itself, so what a demo user sees is the deterministic machinery — length
    floor, target identity, claim minting, rematch — with the model judgment
    held constant. It demonstrates the loop; it does not demonstrate
    assessment quality, which no demo could.
    """

    def _assessment(self, prompt: str) -> dict[str, Any]:
        target = prompt.split("----- TARGET REQUIREMENT -----", 1)[1]
        requirement_id = target.split('"requirement_id": "')[1].split('"')[0]
        answer = (
            prompt.split("----- CANDIDATE ANSWER -----", 1)[1].strip().splitlines()[0]
            if "----- CANDIDATE ANSWER -----" in prompt
            else ""
        )
        return {
            "target_requirement_id": requirement_id,
            "is_valid": True,
            "relevance_reason": "Demo assessor: the answer is taken as given.",
            "specificity_reason": "Demo assessor: no quality judgment is made.",
            "accepted_claim": answer.strip() or None,
        }

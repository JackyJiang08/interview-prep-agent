"""Runtime settings.

Every tunable lives in a config file, never in the code. Resolution order is
explicit argument, then the ``IPA_CONFIG`` environment variable, then the
packaged default. No path in this module is absolute.

A ``.env`` file in the working directory is loaded before the environment is
read, so credentials and tracing switches have one documented home. Values
already present in the environment win over the file.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"

ENV_CONFIG_PATH = "IPA_CONFIG"


class Settings(BaseModel):
    """Validated pipeline settings."""

    match_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    max_matches_per_requirement: int = Field(default=3, ge=1)
    write_stage_artifacts: bool = True

    # Bounds on how many requirements one run may produce. Deliberately wide:
    # they are a guard against degenerate extraction — nothing at all, or a
    # runaway list — not an opinion about how long a posting should be. The
    # extraction prompt asks for a much narrower range, and a count far outside
    # it is a signal worth failing on.
    min_requirements: int = Field(default=1, ge=0)
    max_requirements: int = Field(default=50, ge=1)

    # Bounds on the decision loop, enforced by code rather than suggested in
    # a prompt. The question ceiling is optional: None means every gap is
    # asked about exactly once. The action budget defaults to the size of the
    # gap queue plus the two generation runs, and is always clamped by the
    # hard cap — a backstop against a loop that cycles, not an opinion about
    # how long a run should be. Answers shorter than the clarification floor
    # are rejected in code before any model judgment is consulted.
    max_agent_actions: int | None = Field(default=None, ge=1)
    agent_action_cap: int = Field(default=32, ge=1)
    max_questions_per_run: int | None = Field(default=None, ge=0)
    min_clarification_length: int = Field(default=24, ge=0)

    # Bounds on the web session layer, the same discipline the agent has:
    # exceeding any of them is a structured refusal, never a crash. CORS
    # defaults to no cross-origin access at all.
    max_concurrent_sessions: int = Field(default=8, ge=1)
    max_sessions_per_ip: int = Field(default=3, ge=1)
    session_ttl_seconds: int = Field(default=1800, ge=1)
    max_jd_chars: int = Field(default=20_000, ge=1)
    max_evidence_chars: int = Field(default=50_000, ge=1)
    max_answer_chars: int = Field(default=4_000, ge=1)
    max_round_chars: int = Field(default=2_000, ge=1)
    cors_origins: list[str] = Field(default_factory=list)


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from YAML.

    Args:
        path: Explicit config file. Falls back to ``IPA_CONFIG`` and then to
            the packaged default.

    Returns:
        Validated settings. Defaults apply when the file is absent or empty.
    """
    # Existing environment variables take precedence over the file.
    load_dotenv(override=False)
    resolved = path or _from_environment() or DEFAULT_CONFIG_PATH
    if not Path(resolved).is_file():
        return Settings()

    with open(resolved, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    return Settings(**raw)


def _from_environment() -> Path | None:
    value = os.environ.get(ENV_CONFIG_PATH)
    return Path(value) if value else None

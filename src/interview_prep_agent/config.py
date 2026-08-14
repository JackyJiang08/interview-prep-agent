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

    # Bounds on the decision loop. The action budget caps how many actions a
    # run may take before it is stopped by code; the question budget caps how
    # many times it may interrupt a human. Both are hard ceilings enforced by
    # authorization, not suggestions in a prompt.
    max_agent_actions: int = Field(default=4, ge=1)
    max_questions_per_run: int = Field(default=1, ge=0)


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

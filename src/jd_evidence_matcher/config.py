"""Runtime settings.

Every tunable lives in a config file, never in the code. Resolution order is
explicit argument, then the ``JDEM_CONFIG`` environment variable, then the
packaged default. No path in this module is absolute.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"

ENV_CONFIG_PATH = "JDEM_CONFIG"


class Settings(BaseModel):
    """Validated pipeline settings."""

    match_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    max_matches_per_requirement: int = Field(default=3, ge=1)
    write_stage_artifacts: bool = True


def load_settings(path: Optional[Path] = None) -> Settings:
    """Load settings from YAML.

    Args:
        path: Explicit config file. Falls back to ``JDEM_CONFIG`` and then to
            the packaged default.

    Returns:
        Validated settings. Defaults apply when the file is absent or empty.
    """
    resolved = path or _from_environment() or DEFAULT_CONFIG_PATH
    if not Path(resolved).is_file():
        return Settings()

    with open(resolved, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    return Settings(**raw)


def _from_environment() -> Optional[Path]:
    value = os.environ.get(ENV_CONFIG_PATH)
    return Path(value) if value else None

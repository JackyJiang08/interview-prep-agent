"""Shared fixtures and paths for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_prep_agent import load_evidence, load_job_description

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"


@pytest.fixture
def sample_job_description() -> str:
    return load_job_description(EXAMPLES / "sample_job_description.txt")


@pytest.fixture
def sample_evidence():
    return load_evidence(EXAMPLES / "sample_evidence.yaml")

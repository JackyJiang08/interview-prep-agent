"""Reading job-description text and evidence corpora from disk."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import EvidenceItem


class CorpusError(ValueError):
    """Raised when an input file cannot be read as a valid corpus."""


def load_job_description(path: str | Path) -> str:
    """Read a job description as plain text."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise CorpusError(f"job description at {path} is empty")
    return text


def load_evidence(path: str | Path) -> list[EvidenceItem]:
    """Read an evidence corpus from a YAML or JSON list.

    Each entry needs ``id`` and ``summary``; ``skills`` and ``impact`` are
    optional. Identifiers must be unique, because every match cites one.
    """
    source = Path(path)
    raw_text = source.read_text(encoding="utf-8")

    if source.suffix.lower() == ".json":
        payload = json.loads(raw_text)
    else:
        payload = yaml.safe_load(raw_text)

    if isinstance(payload, dict) and "evidence" in payload:
        payload = payload["evidence"]

    if not isinstance(payload, list):
        raise CorpusError(f"evidence at {path} must be a list of items")

    try:
        items = [EvidenceItem(**entry) for entry in payload]
    except (TypeError, ValidationError) as error:
        raise CorpusError(f"invalid evidence in {path}: {error}") from error

    identifiers = [item.id for item in items]
    if len(set(identifiers)) != len(identifiers):
        raise CorpusError("evidence identifiers must be unique")

    return items

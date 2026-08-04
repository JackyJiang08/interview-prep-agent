"""Reading job-description text and evidence corpora from disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Union

import yaml
from pydantic import ValidationError

from .models import EvidenceItem


class CorpusError(ValueError):
    """Raised when an input file cannot be read as a valid corpus."""


def load_job_description(path: Union[str, Path]) -> str:
    """Read a job description as plain text."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise CorpusError("job description at {} is empty".format(path))
    return text


def load_evidence(path: Union[str, Path]) -> List[EvidenceItem]:
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
        raise CorpusError("evidence at {} must be a list of items".format(path))

    try:
        items = [EvidenceItem(**entry) for entry in payload]
    except (TypeError, ValidationError) as error:
        raise CorpusError("invalid evidence in {}: {}".format(path, error))

    identifiers = [item.id for item in items]
    if len(set(identifiers)) != len(identifiers):
        raise CorpusError("evidence identifiers must be unique")

    return items

"""Stage 1, model-backed - extract requirements through a provider.

The alternative to :mod:`.extract`, which splits on list markers. This path
reads postings that path cannot: prose paragraphs, and lines that bundle
several demands into one sentence.

It buys that with a dependency on a model, so nothing here trusts the response.
The reply is validated against ``RequirementExtraction``, then checked for
the fields only this path can supply, and only then handed on to the same
grounding gate the lexical path faces.
"""

from __future__ import annotations

from typing import Any

from ..models import Requirement, RequirementExtraction
from ..providers import ProviderError, StructuredModel
from .prompt import build_extraction_prompt

# Fields the lexical path leaves unset and this path must not.
MODEL_REQUIRED_FIELDS = ("source_quote", "category", "importance", "requirement_type")


def response_schema() -> dict[str, Any]:
    """Return the JSON Schema requested from the provider."""
    return RequirementExtraction.model_json_schema()


def parse_extraction(payload: Any) -> list[Requirement]:
    """Validate a provider response into requirements.

    Args:
        payload: Whatever the provider parsed. May be a mapping, or an object
            the SDK already built.

    Returns:
        The validated requirements, in the order returned.

    Raises:
        ProviderError: If the payload does not satisfy the schema, or omits a
            field this path is responsible for supplying.
    """
    try:
        extraction = RequirementExtraction.model_validate(payload, from_attributes=True)
    except Exception as error:  # noqa: BLE001 - pydantic raises several types
        raise ProviderError(
            f"model response did not match the requested schema: {error}"
        ) from error

    for item in extraction.requirements:
        missing = [field for field in MODEL_REQUIRED_FIELDS if getattr(item, field) is None]
        if missing:
            raise ProviderError(f"model response omitted {', '.join(missing)} for {item.id}")

    return extraction.requirements


def extract_requirements_with_model(
    job_description: str, model: StructuredModel
) -> list[Requirement]:
    """Extract requirements from a posting using a provider.

    Args:
        job_description: The posting as plain text.
        model: Any implementation of the provider seam.

    Returns:
        Validated requirements. Grounding is checked separately, by the gate,
        so that both extraction paths are held to the same standard.

    Raises:
        ProviderError: If the call fails or the response cannot be used.
    """
    payload = model.generate_json(build_extraction_prompt(job_description), response_schema())
    return parse_extraction(payload)

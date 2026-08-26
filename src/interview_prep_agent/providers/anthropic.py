"""Anthropic implementation of the structured-model seam.

The third implementation, and the second test of the seam's promise that a
provider is one file here and nothing else. The vendor SDK is imported when
the client is first needed rather than at module import or construction, so
holding a key costs nothing until a request is made and the default paths
stay usable without the dependency.

The schema is sent through the SDK's structured-output mechanism, so the
response arrives as JSON shaped to it. It is still only a request: what
comes back is parsed here and validated by the caller, never trusted raw.

This dialect rejects value bounds. Constrained decoding accepts no
``minItems``/``maxItems`` beyond 0 and 1, no ``minimum``/``maximum``, no
``minLength``/``maxLength``, no ``pattern`` — a request carrying one is a
400. The SDK ships a transform for exactly this, and every schema goes
through it here, in this file, and nowhere else.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .base import ProviderError, StructuredModel

ENV_API_KEY = "ANTHROPIC_API_KEY"
ENV_MODEL = "ANTHROPIC_MODEL"

DEFAULT_MODEL = "claude-opus-5"

# Every stage here asks for one structured record; none comes close to this.
MAX_OUTPUT_TOKENS = 16_000


class AnthropicModel(StructuredModel):
    """Structured generation through the Anthropic SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Resolve configuration; the client itself is built on first use.

        Args:
            api_key: Overrides ``ANTHROPIC_API_KEY``.
            model: Overrides ``ANTHROPIC_MODEL``, which defaults to
                :data:`DEFAULT_MODEL`.

        Raises:
            ProviderError: If no key is available.
        """
        resolved_key = api_key or os.environ.get(ENV_API_KEY)
        if not resolved_key:
            raise ProviderError(
                f"{ENV_API_KEY} is not set. Export a key, or use the lexical "
                "extractor and matcher, which need no credentials."
            )
        self._api_key = resolved_key
        self._model = model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL
        self._client: Any = None

    @property
    def name(self) -> str:
        return self._model

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as error:  # pragma: no cover - depends on install
                raise ProviderError(
                    "the anthropic package is not installed; run 'pip install -r requirements.txt'."
                ) from error
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        """Request JSON conforming to ``response_schema``.

        The schema goes out as the response format, so the model's output is
        constrained to it rather than salvaged from prose afterwards. A
        declined request, an empty response and unparseable content are each
        a ``ProviderError``; a response that parses is returned for the
        caller to validate.
        """
        client = self._ensure_client()
        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {"type": "json_schema", "schema": _request_schema(response_schema)}
                },
            )
        except Exception as error:  # noqa: BLE001 - vendor errors are not a taxonomy
            raise ProviderError(f"Anthropic request failed: {error}") from error

        if getattr(message, "stop_reason", None) == "refusal":
            raise ProviderError("Anthropic declined the request.")
        text = next(
            (block.text for block in message.content if getattr(block, "type", None) == "text"),
            None,
        )
        if not text:
            raise ProviderError("Anthropic returned no content.")
        try:
            return json.loads(text)
        except ValueError as error:
            raise ProviderError(f"Anthropic returned unparseable JSON: {error}") from error


def _request_schema(response_schema: dict[str, Any]) -> dict[str, Any]:
    """The schema as this API will accept it.

    The SDK's own transform strips the bounds the API rejects — array
    sizes beyond 0 and 1, numeric ranges, string lengths, patterns — into
    the description, and closes every object. The behavior contract is
    unchanged by this: the caller still validates the parsed response
    against the full Pydantic model, so a stripped bound is enforced
    there, after parsing, exactly as it is for every other provider. What
    changes is only what the model is asked for, never what is accepted.
    """
    from anthropic import transform_schema

    return transform_schema(response_schema)

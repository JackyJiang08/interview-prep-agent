"""Gemini implementation of the structured-model seam.

The vendor SDK is imported inside the constructor rather than at module import,
so the default lexical path stays usable if the dependency is absent or broken.
"""

from __future__ import annotations

import os
from typing import Any

from .base import ProviderError, StructuredModel

ENV_API_KEY = "GEMINI_API_KEY"
ENV_MODEL = "GEMINI_MODEL"

DEFAULT_MODEL = "gemini-3.5-flash-lite"


class GeminiModel(StructuredModel):
    """Structured generation through the Google Generative AI SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Build a client.

        Args:
            api_key: Overrides ``GEMINI_API_KEY``.
            model: Overrides ``GEMINI_MODEL``, which defaults to
                :data:`DEFAULT_MODEL`.

        Raises:
            ProviderError: If no key is available or the SDK is not installed.
        """
        resolved_key = api_key or os.environ.get(ENV_API_KEY)
        if not resolved_key:
            raise ProviderError(
                f"{ENV_API_KEY} is not set. Export a key, or use the lexical "
                "extractor and matcher, which need no credentials."
            )

        try:
            from google import genai
        except ImportError as error:  # pragma: no cover - depends on install
            raise ProviderError(
                "google-genai is not installed; run 'pip install -r requirements.txt'."
            ) from error

        self._model = model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL
        self._client = genai.Client(api_key=resolved_key)

    @property
    def name(self) -> str:
        return self._model

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        """Request JSON conforming to ``response_schema``.

        The schema is sent to the provider so the response arrives structured
        rather than as prose to be salvaged. It is still only a request: the
        caller validates what comes back.
        """
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=response_schema,
                ),
            )
        except Exception as error:  # noqa: BLE001 - vendor errors are not a taxonomy
            raise ProviderError(f"Gemini request failed: {error}") from error

        if response.parsed is None:
            raise ProviderError("Gemini returned no parseable JSON payload.")

        return response.parsed

"""Azure OpenAI implementation of the structured-model seam.

The second implementation, written to answer a question the first one only
asserted: whether the seam's promise — adding a provider means adding a file
here and nothing else — actually holds. See ``docs/DECISIONS.md``.

The vendor SDK is imported inside the constructor rather than at module
import, so the default paths stay usable if the dependency is absent.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .base import ProviderError, StructuredModel
from .schema import close_schema

ENV_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
ENV_API_KEY = "AZURE_OPENAI_API_KEY"
ENV_DEPLOYMENT = "AZURE_OPENAI_DEPLOYMENT"
ENV_API_VERSION = "AZURE_OPENAI_API_VERSION"

DEFAULT_API_VERSION = "2024-10-21"

# The response format wants a schema name; the model's own title is the most
# informative one available and needs no extra plumbing.
DEFAULT_SCHEMA_NAME = "structured_response"


class AzureOpenAIModel(StructuredModel):
    """Structured generation through an Azure OpenAI deployment."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
    ) -> None:
        """Build a client.

        Args:
            api_key: Overrides ``AZURE_OPENAI_API_KEY``.
            endpoint: Overrides ``AZURE_OPENAI_ENDPOINT``.
            deployment: Overrides ``AZURE_OPENAI_DEPLOYMENT`` — the deployment
                name, which Azure uses where other providers use a model name.
            api_version: Overrides ``AZURE_OPENAI_API_VERSION``.

        Raises:
            ProviderError: If configuration is missing or the SDK is absent.
        """
        resolved_key = api_key or os.environ.get(ENV_API_KEY)
        resolved_endpoint = endpoint or os.environ.get(ENV_ENDPOINT)
        resolved_deployment = deployment or os.environ.get(ENV_DEPLOYMENT)

        missing = [
            name
            for name, value in (
                (ENV_API_KEY, resolved_key),
                (ENV_ENDPOINT, resolved_endpoint),
                (ENV_DEPLOYMENT, resolved_deployment),
            )
            if not value
        ]
        if missing:
            raise ProviderError(
                f"{' and '.join(missing)} is not set. Export the Azure "
                "settings, or run with the lexical extractor and matcher, "
                "which need no credentials."
            )

        try:
            from openai import AzureOpenAI
        except ImportError as error:  # pragma: no cover - depends on install
            raise ProviderError(
                "the openai package is not installed; run 'pip install -r requirements.txt'."
            ) from error

        self._deployment = str(resolved_deployment)
        self._client = AzureOpenAI(
            api_key=resolved_key,
            azure_endpoint=str(resolved_endpoint),
            api_version=api_version or os.environ.get(ENV_API_VERSION) or DEFAULT_API_VERSION,
        )

    @property
    def name(self) -> str:
        return self._deployment

    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        """Request JSON conforming to ``response_schema``.

        The schema is sent as a strict json_schema response format, so the
        response arrives structured rather than as prose to be salvaged. It is
        still only a request: the caller validates what comes back.
        """
        schema = close_schema(response_schema)
        try:
            completion = self._client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": prompt}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_schema.get("title") or DEFAULT_SCHEMA_NAME,
                        "schema": schema,
                        "strict": True,
                    },
                },
            )
        except Exception as error:  # noqa: BLE001 - vendor errors are not a taxonomy
            raise ProviderError(f"Azure OpenAI request failed: {error}") from error

        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            raise ProviderError("Azure OpenAI returned no content.")
        try:
            return json.loads(content)
        except ValueError as error:
            raise ProviderError(f"Azure OpenAI returned unparseable JSON: {error}") from error


# The adaptation that used to live here, kept under its old name. It moved to
# ``schema.py`` when the third provider needed it too.
_strict_schema = close_schema

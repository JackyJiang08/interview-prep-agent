"""The seam between this package and any model provider.

Everything above this module works in terms of ``StructuredModel``. No
stage imports a vendor SDK, constructs a client, or knows a provider's name, so
adding a second provider means adding a file here and nothing else. That is
what makes the provider-agnostic claim in the README true rather than aspirational.

The contract is deliberately narrow: one call, taking a prompt and a JSON
schema, returning whatever the provider parsed. Validating that return value
against a Pydantic model is the caller's job, and the caller does it — a
provider is never trusted to have honoured the schema it was given.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderError(RuntimeError):
    """Raised when a provider is unusable or its response cannot be used.

    Covers missing credentials, a failed call, and a response that arrived but
    could not be parsed. It deliberately does not cover a response that parsed
    but failed validation; that is a gate concern, raised further up.
    """


class StructuredModel(ABC):
    """A model that returns JSON conforming to a supplied schema."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier recorded alongside anything this model produced."""

    @abstractmethod
    def generate_json(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        """Return the provider's parsed JSON response.

        Args:
            prompt: The full prompt, including any source document.
            response_schema: JSON Schema the response is asked to satisfy.

        Returns:
            The parsed response, structurally unverified.

        Raises:
            ProviderError: If the call fails or the response cannot be parsed.
        """

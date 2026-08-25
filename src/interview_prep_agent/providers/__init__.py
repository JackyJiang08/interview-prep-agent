"""Model providers, behind one abstract seam.

Import :func:`build_model` rather than a concrete provider, so that adding a
second one never requires touching a calling site.
"""

from __future__ import annotations

from .base import ProviderError, StructuredModel

DEFAULT_PROVIDER = "gemini"
PROVIDERS = ("gemini", "azure")


def build_model(provider: str = DEFAULT_PROVIDER, **options: object) -> StructuredModel:
    """Construct the named provider.

    Args:
        provider: Registered provider name.
        **options: Passed to the provider constructor, for example ``api_key``
            or ``model``.

    Raises:
        ProviderError: If the name is unknown, or the provider cannot be built.
    """
    if provider == "gemini":
        from .gemini import GeminiModel

        return GeminiModel(**options)  # type: ignore[arg-type]
    if provider == "azure":
        from .azure import AzureOpenAIModel

        return AzureOpenAIModel(**options)  # type: ignore[arg-type]

    raise ProviderError(f"Unknown model provider {provider!r}; known: {', '.join(PROVIDERS)}")


__all__ = [
    "DEFAULT_PROVIDER",
    "PROVIDERS",
    "ProviderError",
    "StructuredModel",
    "build_model",
]

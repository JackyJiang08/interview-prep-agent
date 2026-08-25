"""The seam between this package and any search provider.

Mirrors the model-provider seam: everything above works in terms of
``SearchProvider``, no stage imports a vendor SDK or calls a network API
directly, and adding a second provider means adding a file here. The
contract is deliberately narrow — one query in, plain results out — and it
speaks to search APIs only: no scraping, no site-specific clients.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class SearchError(RuntimeError):
    """Raised when a provider is unusable or a call fails."""


class SearchResult(TypedDict):
    """One raw result, before normalization into a finding."""

    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    """A provider that answers one query with a bounded result list."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier recorded alongside anything this provider returned."""

    @abstractmethod
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return up to ``max_results`` results for ``query``.

        Raises:
            SearchError: If the call fails.
        """

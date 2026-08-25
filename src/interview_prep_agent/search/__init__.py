"""Search providers, behind one abstract seam.

An absent key never errors: ``maybe_build_search_provider`` returns ``None``
and the research stage's search path is simply inactive.
"""

from __future__ import annotations

import os

from .base import SearchError, SearchProvider, SearchResult


def maybe_build_search_provider() -> SearchProvider | None:
    """Return the configured provider, or None when no key is present."""
    if os.environ.get("TAVILY_API_KEY"):
        from .tavily import TavilySearch

        return TavilySearch()
    return None


__all__ = [
    "SearchError",
    "SearchProvider",
    "SearchResult",
    "maybe_build_search_provider",
]

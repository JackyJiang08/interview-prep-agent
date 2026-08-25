"""Tavily implementation of the search seam.

Uses the plain REST endpoint through the standard library, so the runtime
dependency set is unchanged. The key comes from ``TAVILY_API_KEY``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import SearchError, SearchProvider, SearchResult

ENV_API_KEY = "TAVILY_API_KEY"
ENDPOINT = "https://api.tavily.com/search"
TIMEOUT_SECONDS = 15


class TavilySearch(SearchProvider):
    """Search through the Tavily REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        resolved = api_key or os.environ.get(ENV_API_KEY)
        if not resolved:
            raise SearchError(f"{ENV_API_KEY} is not set")
        self._api_key = resolved

    @property
    def name(self) -> str:
        return "tavily"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        payload = json.dumps(
            {"api_key": self._api_key, "query": query, "max_results": max_results}
        ).encode("utf-8")
        request = urllib.request.Request(
            ENDPOINT, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            raise SearchError(f"search request failed: {error}") from error

        results: list[SearchResult] = []
        for row in body.get("results", []):
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            snippet = str(row.get("content") or "").strip()
            if title and url:
                results.append({"title": title, "url": url, "snippet": snippet})
        return results[:max_results]

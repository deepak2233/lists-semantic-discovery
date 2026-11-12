"""Provider contract. Live queries go only to a fixed Brave API endpoint."""

import asyncio
import html
import json
import re
import time
from dataclasses import dataclass
from importlib.resources import files
from typing import Protocol

import httpx

from .safety import canonical_url, redact


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    snippet: str
    provider_rank: int


class ProviderUnavailable(Exception):
    pass


class SearchProvider(Protocol):
    async def search(self, query: str) -> list[Candidate]: ...


class DemoProvider:
    def __init__(self) -> None:
        self.documents = json.loads(
            files("lists_api").joinpath("data/demo_corpus.json").read_text()
        )

    async def search(self, query: str) -> list[Candidate]:
        # All fixtures enter the ranker. No claim that this is web retrieval.
        return [
            Candidate(d["url"], d["title"], d["snippet"], i + 1)
            for i, d in enumerate(self.documents)
        ]


class BraveProvider:
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, client: httpx.AsyncClient, key: str, timeout: float = 3.0) -> None:
        self.client, self.key, self.timeout = client, key, timeout
        self.failures = 0
        self.open_until = 0.0
        self.lock = asyncio.Lock()

    async def search(self, query: str) -> list[Candidate]:
        async with self.lock:
            if time.monotonic() < self.open_until:
                raise ProviderUnavailable("Search temporarily unavailable")
        try:
            async with asyncio.timeout(self.timeout):
                # Two bounded pages, one query: up to 40 candidates. Respect provider plan limits.
                batches = []
                for offset in (0, 1):
                    response = await self.client.get(
                        self.ENDPOINT,
                        params={
                            "q": query,
                            "count": 20,
                            "offset": offset,
                            "search_lang": "en",
                            "safesearch": "strict",
                            "text_decorations": "false",
                            "result_filter": "web",
                        },
                        headers={"X-Subscription-Token": self.key, "Accept": "application/json"},
                    )
                    response.raise_for_status()
                    # Cap memory before JSON parsing. HTTPX has already buffered this response.
                    if len(response.content) > 2_000_000:
                        raise ValueError("Oversized provider response")
                    payload = response.json()
                    batch = payload.get("web", {}).get("results", [])
                    if not isinstance(batch, list):
                        raise ValueError("Invalid provider schema")
                    batches.extend(batch[:20])
            candidates = []
            for rank, d in enumerate(batches, 1):
                try:
                    url = canonical_url(d["url"])
                    title = _plain(d.get("title", ""), 300)
                    snippet = _plain(d.get("description", ""), 700)
                    if title and snippet:
                        candidates.append(Candidate(url, title, snippet, rank))
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, AttributeError):
            async with self.lock:
                self.failures += 1
                if self.failures >= 3:
                    self.open_until = time.monotonic() + 30
            raise ProviderUnavailable("Search temporarily unavailable") from None
        async with self.lock:
            self.failures = 0
            self.open_until = 0
        return candidates


def _plain(value: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid provider text")
    return redact(re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))))[:limit]

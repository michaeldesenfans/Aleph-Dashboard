"""Brave Search adapter used as selective discovery radar."""

from __future__ import annotations

import logging

import requests

from server.config import BRAVE_DEFAULT_COUNT, BRAVE_SEARCH_API_KEY

logger = logging.getLogger(__name__)

BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"
BRAVE_WEB_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveBudgetExceeded(Exception):
    pass


class BraveAdapter:
    def __init__(self, max_monthly_calls: int = 2000):
        self._calls_this_session = 0
        self._max_monthly = max_monthly_calls

    @property
    def calls_used(self) -> int:
        return self._calls_this_session

    def search_news(self, query: str, count: int = BRAVE_DEFAULT_COUNT, freshness: str = "pw") -> list[dict]:
        return self._search(BRAVE_NEWS_URL, query, count, freshness)

    def search_web(self, query: str, count: int = BRAVE_DEFAULT_COUNT, freshness: str = "pw") -> list[dict]:
        return self._search(BRAVE_WEB_URL, query, count, freshness)

    def _search(self, url: str, query: str, count: int, freshness: str) -> list[dict]:
        if not BRAVE_SEARCH_API_KEY:
            logger.warning("BRAVE_SEARCH_API_KEY not set; Brave discovery disabled")
            return []
        if self._calls_this_session >= self._max_monthly:
            raise BraveBudgetExceeded("Session budget exhausted")

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
        }
        params = {
            "q": query,
            "count": max(1, min(count, 10)),
            "freshness": freshness,
        }

        resp = requests.get(url, headers=headers, params=params, timeout=12)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            if resp.status_code == 429:
                raise BraveBudgetExceeded("Rate limited by Brave") from exc
            raise

        data = resp.json()
        self._calls_this_session += 1

        items = data.get("results", []) or (data.get("web") or {}).get("results", [])
        results: list[dict] = []
        for item in items:
            meta_url = item.get("meta_url")
            hostname = meta_url.get("hostname", "") if isinstance(meta_url, dict) else ""
            results.append(
                {
                    "url": item.get("url", ""),
                    "canonical_url": item.get("url", ""),
                    "title_raw": item.get("title", ""),
                    "snippet_raw": item.get("description", ""),
                    "content_raw": item.get("description", ""),
                    "published_at": item.get("page_age") or item.get("age") or "",
                    "source_name": hostname,
                    "metadata_json": "{}",
                }
            )
        return results

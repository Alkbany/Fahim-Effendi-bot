import asyncio
import logging
import os
from urllib.parse import urlsplit

from ddgs import DDGS

logger = logging.getLogger("fahim.search")


class SearchUnavailableError(RuntimeError):
    """Raised when every configured DDGS search backend fails."""


class SearchService:
    def __init__(
        self,
        max_results=5,
        timeout=10,
        max_query_chars=500,
        backend=None,
        region=None,
    ):
        self.max_results = max(1, min(int(max_results), 10))
        self.timeout = max(3, min(int(timeout), 30))
        self.max_query_chars = max(1, int(max_query_chars))
        self.backend = (backend or os.getenv("DDGS_BACKEND", "auto")).strip() or "auto"
        self.region = (region or os.getenv("DDGS_REGION", "wt-wt")).strip() or "wt-wt"

    def _search_sync(self, query):
        # DDGS performs the provider requests in worker threads and applies this
        # timeout to its outbound HTTP operations. "auto" lets the library use
        # its available text-search backends instead of pinning the bot to one.
        return DDGS(timeout=self.timeout).text(
            query,
            region=self.region,
            max_results=self.max_results,
            safesearch="moderate",
            backend=self.backend,
        )

    @staticmethod
    def _normalise_result(item):
        if not isinstance(item, dict):
            return None

        url = item.get("href") or item.get("url")
        if not isinstance(url, str):
            return None

        url = url.strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None

        title = str(item.get("title") or "بدون عنوان").strip()[:200]
        snippet = str(item.get("body") or item.get("snippet") or "").strip()[:1000]
        return {
            "title": title or "بدون عنوان",
            "url": url[:1000],
            "snippet": snippet,
        }

    async def search(self, query):
        if not isinstance(query, str) or not query.strip():
            return []

        query = query.strip()[:self.max_query_chars]

        try:
            results = await asyncio.to_thread(self._search_sync, query)
        except Exception as error:
            logger.exception("External web search failed.")
            raise SearchUnavailableError("All web-search backends failed.") from error

        clean_results = []
        seen_urls = set()
        for item in results or []:
            clean = self._normalise_result(item)
            if clean is None or clean["url"] in seen_urls:
                continue
            seen_urls.add(clean["url"])
            clean_results.append(clean)
            if len(clean_results) >= self.max_results:
                break

        logger.info(
            "Search completed | results=%d | backend=%s | region=%s",
            len(clean_results),
            self.backend,
            self.region,
        )
        return clean_results

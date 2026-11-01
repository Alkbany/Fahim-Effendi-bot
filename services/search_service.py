import asyncio
import logging

from ddgs import DDGS

logger = logging.getLogger("fahim.search")


class SearchService:
    def __init__(self, max_results=5, timeout=10, max_query_chars=500):
        self.max_results = max_results
        self.timeout = timeout
        self.max_query_chars = max_query_chars

    def _search_sync(self, query):
        # DDGS applies this timeout to its outbound requests, so a stalled
        # search provider cannot hold a worker thread indefinitely.
        return DDGS(timeout=self.timeout).text(
            query,
            max_results=self.max_results,
            safesearch="moderate",
        )

    async def search(self, query):
        if not isinstance(query, str) or not query.strip():
            return []

        query = query.strip()[:self.max_query_chars]

        try:
            results = await asyncio.to_thread(
                self._search_sync,
                query,
            )

            clean_results = []

            for item in results or []:
                if not isinstance(item, dict):
                    continue

                url = item.get("href")
                if not isinstance(url, str):
                    continue

                if not url.startswith(("https://", "http://")):
                    continue

                clean_results.append({
                    "title": str(item.get("title") or "بدون عنوان")[:200],
                    "url": url[:1000],
                    "snippet": str(item.get("body") or "")[:1000],
                })

            logger.info("Search returned %d results.", len(clean_results))
            return clean_results

        except Exception:
            logger.exception("External search failed.")
            return []

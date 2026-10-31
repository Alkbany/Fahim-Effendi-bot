import unittest
from unittest.mock import patch

from services.search_service import SearchService


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):

    async def test_returns_clean_search_results(self):
        service = SearchService()

        fake_results = [{
            "title": "Python Docs",
            "href": "https://docs.python.org/",
            "body": "Official documentation",
        }]

        with patch.object(
            service, "_search_sync", return_value=fake_results
        ):
            results = await service.search("Python")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Python Docs")
        self.assertEqual(results[0]["url"], "https://docs.python.org/")

    async def test_empty_query_returns_empty_list(self):
        service = SearchService()
        results = await service.search("   ")
        self.assertEqual(results, [])

    async def test_ignores_invalid_urls(self):
        service = SearchService()

        fake_results = [
            {"title": "Invalid", "href": "javascript:alert(1)"},
            {"title": "Valid", "href": "https://example.com"},
        ]

        with patch.object(
            service, "_search_sync", return_value=fake_results
        ):
            results = await service.search("test")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.com")

    async def test_search_failure_returns_empty_list(self):
        service = SearchService()

        with patch.object(
            service, "_search_sync",
            side_effect=RuntimeError("Search failed"),
        ):
            results = await service.search("test")

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()

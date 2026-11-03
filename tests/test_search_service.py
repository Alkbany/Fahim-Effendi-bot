import unittest
from unittest.mock import patch

from services.search_service import SearchService, SearchUnavailableError


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_clean_search_results(self):
        service = SearchService()
        fake_results = [{
            "title": "Python Docs",
            "href": "https://docs.python.org/",
            "body": "Official documentation",
        }]
        with patch.object(service, "_search_sync", return_value=fake_results):
            results = await service.search("Python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Python Docs")
        self.assertEqual(results[0]["url"], "https://docs.python.org/")

    async def test_empty_query_returns_empty_list(self):
        self.assertEqual(await SearchService().search("   "), [])

    async def test_ignores_invalid_urls_and_duplicates(self):
        service = SearchService()
        fake_results = [
            {"title": "Invalid", "href": "javascript:alert(1)"},
            {"title": "No host", "href": "https:///missing-host"},
            {"title": "Valid", "href": "https://example.com"},
            {"title": "Duplicate", "href": "https://example.com"},
        ]
        with patch.object(service, "_search_sync", return_value=fake_results):
            results = await service.search("test")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.com")

    async def test_provider_failure_is_not_reported_as_no_results(self):
        service = SearchService()
        with patch.object(
            service, "_search_sync", side_effect=RuntimeError("provider down")
        ):
            with self.assertRaises(SearchUnavailableError):
                await service.search("test")

    async def test_ddgs_receives_configured_network_timeout_and_backend(self):
        with patch("services.search_service.DDGS") as ddgs:
            ddgs.return_value.text.return_value = []
            service = SearchService(timeout=7, backend="bing", region="wt-wt")
            service._search_sync("Python")
        ddgs.assert_called_once_with(timeout=7)
        ddgs.return_value.text.assert_called_once_with(
            "Python",
            region="wt-wt",
            max_results=5,
            safesearch="moderate",
            backend="bing",
        )

    async def test_query_is_trimmed_and_length_limited(self):
        service = SearchService(max_query_chars=500)
        with patch.object(service, "_search_sync", return_value=[]) as search:
            await service.search("  " + ("x" * 600) + "  ")
        search.assert_called_once_with("x" * 500)

    async def test_limits_results_to_configured_count(self):
        service = SearchService(max_results=2)
        with patch.object(service, "_search_sync", return_value=[
            {"title": str(i), "href": f"https://example.com/{i}"} for i in range(5)
        ]):
            results = await service.search("test")
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()

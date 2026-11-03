import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from services.ai_service import AIService, EmptyModelResponseError


class AIFallbackTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self):
        ai = AIService.__new__(AIService)
        ai.search_service = None
        ai.personality = "test personality"
        ai.history_limit = 5
        ai.is_emergency_or_safety_request = Mock(return_value=False)
        ai.is_apology_attempt = Mock(return_value=False)
        ai.build_history = Mock(return_value=[])
        ai.get_current_time_context = Mock(return_value="")
        ai.build_memory_context = Mock(return_value="")
        ai.get_answer_priority_instructions = Mock(return_value="")
        ai.request_model = AsyncMock()
        return ai

    async def test_empty_primary_response_uses_fallback_model(self):
        ai = self.make_service()
        ai.request_model.side_effect = [
            EmptyModelResponseError("gemini-primary", None),
            (SimpleNamespace(text="الرد البديل", candidates=[], usage_metadata=None), []),
        ]

        answer = await ai.generate_response("سؤال عادي")

        self.assertEqual(answer, "الرد البديل")
        self.assertEqual(ai.request_model.await_count, 2)
        primary_args = ai.request_model.await_args_list[0].args
        fallback_args = ai.request_model.await_args_list[1].args
        self.assertEqual(primary_args[0], "gemini-3.5-flash-lite")
        self.assertEqual(fallback_args[0], "gemini-3.6-flash")
        self.assertIs(
            ai.request_model.await_args_list[0].kwargs["tool_state"],
            ai.request_model.await_args_list[1].kwargs["tool_state"],
        )

    async def test_safety_block_does_not_retry_on_fallback_model(self):
        ai = self.make_service()
        ai.request_model.side_effect = EmptyModelResponseError(
            "gemini-primary", "SAFETY", retryable=False
        )

        with self.assertRaises(EmptyModelResponseError):
            await ai.generate_response("سؤال محجوب")

        self.assertEqual(ai.request_model.await_count, 1)

    async def test_unavailable_search_is_distinguished_from_empty_results(self):
        ai = AIService.__new__(AIService)

        class BrokenSearch:
            async def search(self, query):
                raise RuntimeError("provider down")

        ai.search_service = BrokenSearch()
        result = await ai.execute_search("query")

        self.assertFalse(result["success"])
        self.assertFalse(result["available"])
        self.assertIn("no verifiable results", result["message"])

    async def test_empty_search_results_are_a_successful_search_with_no_matches(self):
        ai = AIService.__new__(AIService)

        class EmptySearch:
            async def search(self, query):
                return []

        ai.search_service = EmptySearch()
        result = await ai.execute_search("query")

        self.assertFalse(result["success"])
        self.assertTrue(result["available"])
        self.assertEqual(result["results"], [])


if __name__ == "__main__":
    unittest.main()

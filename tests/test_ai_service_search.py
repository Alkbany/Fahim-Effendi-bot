import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from google.genai import types

from services.ai_service import AIService


def make_tool_response(query):
    call = SimpleNamespace(
        name="web_search",
        args={"query": query},
    )
    part = SimpleNamespace(function_call=call)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(
        candidates=[candidate],
        text=None,
        usage_metadata=None,
    )


def make_relationship_tool_response(event_type, details, summary):
    call = SimpleNamespace(
        name="record_relationship_event",
        args={
            "event_type": event_type,
            "details": details,
            "summary": summary,
        },
    )
    part = SimpleNamespace(function_call=call)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(
        candidates=[candidate],
        text=None,
        usage_metadata=None,
    )



def make_combined_tool_response():
    calls = [
        SimpleNamespace(name="web_search", args={"query": "Python"}),
        SimpleNamespace(
            name="record_relationship_event",
            args={
                "event_type": "conflict",
                "details": "إهانة مباشرة لفهيم.",
                "summary": "خلاف سابق مع العضو.",
            },
        ),
    ]
    parts = [SimpleNamespace(function_call=c) for c in calls]
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))],
        text=None,
        usage_metadata=None,
    )

def make_text_response(text):
    return SimpleNamespace(
        candidates=[],
        text=text,
        usage_metadata=None,
    )


class AISearchTests(unittest.IsolatedAsyncioTestCase):

    async def test_executes_search_and_returns_results(self):
        search = Mock()
        search.search = AsyncMock(return_value=[
            {
                "title": "Python Docs",
                "url": "https://docs.python.org/",
                "snippet": "Official documentation",
            }
        ])

        ai = AIService.__new__(AIService)
        ai.search_service = search

        result = await ai.execute_search("Python")

        search.search.assert_awaited_once_with("Python")
        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 1)

    async def test_handles_unavailable_search_service(self):
        ai = AIService.__new__(AIService)
        ai.search_service = None

        result = await ai.execute_search("Python")

        self.assertFalse(result["success"])
        self.assertEqual(result["results"], [])

    async def test_handles_empty_search_results(self):
        search = Mock()
        search.search = AsyncMock(return_value=[])

        ai = AIService.__new__(AIService)
        ai.search_service = search

        result = await ai.execute_search("Unknown query")

        self.assertFalse(result["success"])
        self.assertEqual(result["results"], [])

    async def test_returns_only_sources_cited_by_model(self):
        search = Mock()
        search.search = AsyncMock(return_value=[
            {
                "title": "Python Docs",
                "url": "https://docs.python.org/",
                "snippet": "Official documentation",
            },
            {
                "title": "Python Blog",
                "url": "https://blog.python.org/",
                "snippet": "Release announcements",
            },
        ])

        chat = Mock()
        chat.send_message = AsyncMock(side_effect=[
            make_tool_response("Python documentation"),
            make_text_response(
                "توثيق Python الرسمي متاح هنا [S1]. "
                "معلومة غير موثقة [S99]."
            ),
        ])

        ai = AIService.__new__(AIService)
        ai.search_service = search
        ai.client = Mock()
        ai.client.chats.create.return_value = chat

        response, sources = await ai.request_model(
            "test-model",
            "ابحث عن توثيق Python",
            [],
            "تعليمات الاختبار",
        )

        search.search.assert_awaited_once_with("Python documentation")
        self.assertIn("[S1]", response.text)
        self.assertEqual(
            sources,
            ["- Python Docs: https://docs.python.org/"],
        )
        self.assertNotIn("blog.python.org", "\n".join(sources))

    async def test_does_not_return_uncited_search_sources(self):
        search = Mock()
        search.search = AsyncMock(return_value=[
            {
                "title": "Example",
                "url": "https://example.com/",
                "snippet": "Example result",
            }
        ])

        chat = Mock()
        chat.send_message = AsyncMock(side_effect=[
            make_tool_response("first query"),
            make_text_response("إجابة بدون استشهاد."),
        ])

        ai = AIService.__new__(AIService)
        ai.search_service = search
        ai.client = Mock()
        ai.client.chats.create.return_value = chat

        response, sources = await ai.request_model(
            "test-model",
            "ابحث عن معلومة",
            [],
            "تعليمات الاختبار",
        )

        self.assertEqual(response.text, "إجابة بدون استشهاد.")
        self.assertEqual(sources, [])

    async def test_executes_at_most_one_search_per_request(self):
        search = Mock()
        search.search = AsyncMock(return_value=[
            {
                "title": "Example",
                "url": "https://example.com/",
                "snippet": "Example result",
            }
        ])

        chat = Mock()
        chat.send_message = AsyncMock(side_effect=[
            make_tool_response("first query"),
            make_text_response("Final answer [S1]."),
        ])

        ai = AIService.__new__(AIService)
        ai.search_service = search
        ai.client = Mock()
        ai.client.chats.create.return_value = chat

        response, sources = await ai.request_model(
            "test-model",
            "ابحث عن معلومة",
            [],
            "تعليمات الاختبار",
        )

        search.search.assert_awaited_once_with("first query")
        self.assertEqual(response.text, "Final answer [S1].")
        self.assertEqual(chat.send_message.await_count, 2)

        follow_up_config = chat.send_message.await_args.kwargs["config"]
        mode = follow_up_config.tool_config.function_calling_config.mode
        self.assertEqual(mode, types.FunctionCallingConfigMode.NONE)

        self.assertEqual(len(sources), 1)


    async def test_records_relationship_event(self):
        details = "العضو وجّه إهانة مباشرة لفهيم."
        summary = "يوجد خلاف سابق يحتاج إلى تحفظ."

        chat = Mock()
        chat.send_message = AsyncMock(side_effect=[
            make_relationship_tool_response(
                "conflict", details, summary
            ),
            make_text_response("حاضر يا سيدي."),
        ])

        ai = AIService.__new__(AIService)
        ai.search_service = None
        ai.client = Mock()
        ai.client.chats.create.return_value = chat

        callback = AsyncMock(return_value={"success": True})

        response, sources = await ai.request_model(
            "test-model",
            "رسالة اختبار",
            [],
            "تعليمات الاختبار",
            relationship_event_callback=callback,
        )

        callback.assert_awaited_once_with(
            "conflict", details, summary
        )
        self.assertEqual(response.text, "حاضر يا سيدي.")
        self.assertEqual(sources, [])
        self.assertEqual(chat.send_message.await_count, 2)


    async def test_executes_search_and_relationship_event_together(self):
        search = Mock()
        search.search = AsyncMock(return_value=[
            {
                "title": "Python Docs",
                "url": "https://docs.python.org/",
                "snippet": "Official documentation",
            }
        ])

        chat = Mock()
        chat.send_message = AsyncMock(side_effect=[
            make_combined_tool_response(),
            make_text_response("الإجابة النهائية [S1]."),
        ])

        ai = AIService.__new__(AIService)
        ai.search_service = search
        ai.client = Mock()
        ai.client.chats.create.return_value = chat

        callback = AsyncMock(return_value={"success": True})

        response, sources = await ai.request_model(
            "test-model",
            "ابحث وسجّل الحدث",
            [],
            "تعليمات الاختبار",
            relationship_event_callback=callback,
        )

        search.search.assert_awaited_once_with("Python")
        callback.assert_awaited_once_with(
            "conflict",
            "إهانة مباشرة لفهيم.",
            "خلاف سابق مع العضو.",
        )
        self.assertEqual(response.text, "الإجابة النهائية [S1].")
        self.assertEqual(len(sources), 1)
        self.assertEqual(chat.send_message.await_count, 2)

        follow_up = chat.send_message.await_args.args[0]
        self.assertEqual(len(follow_up), 2)
        self.assertEqual(
            {part.function_response.name for part in follow_up},
            {"web_search", "record_relationship_event"},
        )


    async def test_detects_current_price_questions(self):
        ai = AIService.__new__(AIService)

        self.assertTrue(
            ai.is_current_price_question("أسعار الذهب اليوم في مصر")
        )
        self.assertTrue(
            ai.is_current_price_question("الدولار بكام النهارده؟")
        )
        self.assertFalse(
            ai.is_current_price_question("ما رأيك في ادخار المال؟")
        )
        self.assertFalse(
            ai.is_current_price_question("اشرح لي تاريخ الذهب")
        )

    async def test_forces_price_search_before_model_request(self):
        order = []
        search = Mock()

        async def fake_search(query):
            order.append("search")
            return [{
                "title": "Gold Prices",
                "url": "https://example.com/gold",
                "snippet": "سعر الذهب عيار 21 هو 5000 جنيه.",
            }]

        search.search = AsyncMock(side_effect=fake_search)

        ai = AIService.__new__(AIService)
        ai.search_service = search
        ai.personality = "شخصية فهيم"
        ai.history_limit = 10

        response = make_text_response("سعر الذهب حسب المصدر [S1].")
        ai.request_model = AsyncMock(
            side_effect=lambda *args, **kwargs: (
                order.append("model") or (response, [])
            )
        )

        answer = await ai.generate_response(
            "أسعار الذهب اليوم في مصر"
        )

        self.assertEqual(order, ["search", "model"])
        search.search.assert_awaited_once()
        call_kwargs = ai.request_model.await_args.kwargs
        self.assertEqual(
            call_kwargs["initial_search_sources"][0]["id"],
            "S1",
        )
        self.assertIn("سعر الذهب عيار 21", ai.request_model.await_args.args[3])
        self.assertIn("[S1]", answer)

    async def test_discloses_failed_mandatory_price_search(self):
        search = Mock()
        search.search = AsyncMock(return_value=[])

        ai = AIService.__new__(AIService)
        ai.search_service = search
        ai.personality = "شخصية فهيم"
        ai.history_limit = 10

        response = make_text_response(
            "لا تتوفر لدي بيانات كافية لتحديد السعر."
        )
        ai.request_model = AsyncMock(
            return_value=(response, [])
        )

        answer = await ai.generate_response(
            "سعر الذهب اليوم في مصر"
        )

        system_instruction = (
            ai.request_model.await_args.args[3]
        )
        self.assertIn(
            "[MANDATORY PRICE SEARCH FAILED]",
            system_instruction,
        )
        self.assertIn("لا تذكر أي سعر", system_instruction)
        self.assertIn("بيانات كافية", answer)
        search.search.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

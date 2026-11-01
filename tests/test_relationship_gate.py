import unittest
from unittest.mock import AsyncMock

from services.ai_service import AIService


class RelationshipGateTests(unittest.IsolatedAsyncioTestCase):
    def make_ai(self):
        ai = AIService.__new__(AIService)
        ai.personality = "شخصية فهيم"
        ai.search_service = None
        ai.history_limit = 10
        ai.request_model = AsyncMock()
        return ai

    async def test_pending_conflict_requires_a_genuine_apology_before_ordinary_requests(self):
        ai = self.make_ai()
        ai.request_model.return_value = (
            type("Response", (), {
                "text": "بايثون لغة برمجة سهلة البداية.",
                "candidates": [],
                "usage_metadata": None,
            })(),
            [],
        )

        answer = await ai.generate_response(
            "ممكن تشرحلي بايثون؟",
            memories={"personal": [{
                "key": "relationship_state",
                "status": "awaiting_apology",
                "summary": "خلاف سابق",
            }]},
        )

        self.assertIn("بايثون", answer)
        ai.request_model.assert_awaited_once()
        instruction = ai.request_model.await_args.args[3]
        self.assertIn("Do not answer ordinary requests", instruction)
        self.assertIn("A phrase such as", instruction)
        self.assertIn("without blaming Fahim or making excuses", instruction)
        self.assertNotIn("Always answer the member's current question", instruction)

    async def test_pending_conflict_allows_explicit_apology_attempt(self):
        ai = self.make_ai()
        ai.request_model.return_value = (
            type("Response", (), {
                "text": "سمعت اعتذارك، وهفكر في كلامك.",
                "candidates": [],
                "usage_metadata": None,
            })(),
            [],
        )

        await ai.generate_response(
            "حقك عليا يا فهيم، أنا آسف على اللي قلته.",
            memories={"personal": [{
                "key": "relationship_state",
                "status": "awaiting_apology",
            }]},
        )

        instruction = ai.request_model.await_args.args[3]
        self.assertIn("DETERMINISTIC RELATIONSHIP STATE: AWAITING APOLOGY", instruction)

    async def test_pending_conflict_allows_urgent_safety_request(self):
        ai = self.make_ai()
        ai.request_model.return_value = (
            type("Response", (), {
                "text": "اطلب الإسعاف فورًا وابتعد عن مصدر الخطر.",
                "candidates": [],
                "usage_metadata": None,
            })(),
            [],
        )

        memory_callbacks = {
            "user": AsyncMock(),
            "guild": AsyncMock(),
        }

        await ai.generate_response(
            "في حريق والحقني بسرعة",
            memories={"personal": [{
                "key": "relationship_state",
                "status": "awaiting_apology",
            }]},
            memory_event_callbacks=memory_callbacks,
        )

        instruction = ai.request_model.await_args.args[3]
        self.assertIn("urgent safety request", instruction)
        self.assertIsNone(
            ai.request_model.await_args.kwargs["relationship_event_callback"]
        )
        self.assertIsNone(
            ai.request_model.await_args.kwargs["memory_event_callbacks"]
        )

    async def test_urgent_safety_request_never_records_relationship_events(self):
        for status in ("normal", "reserved"):
            with self.subTest(status=status):
                ai = self.make_ai()
                ai.request_model.return_value = (
                    type("Response", (), {
                        "text": "ابتعد عن مصدر الخطر واطلب المساعدة فورًا.",
                        "candidates": [],
                        "usage_metadata": None,
                    })(),
                    [],
                )
                relationship_callback = AsyncMock()
                memory_callbacks = {
                    "user": AsyncMock(),
                    "guild": AsyncMock(),
                }

                await ai.generate_response(
                    "في حريق والحقني بسرعة",
                    memories={"personal": [{
                        "key": "relationship_state",
                        "status": status,
                    }]},
                    relationship_event_callback=relationship_callback,
                    memory_event_callbacks=memory_callbacks,
                )

                self.assertIsNone(
                    ai.request_model.await_args.kwargs["relationship_event_callback"]
                )
                self.assertIsNone(
                    ai.request_model.await_args.kwargs["memory_event_callbacks"]
                )
                relationship_callback.assert_not_awaited()
                memory_callbacks["user"].assert_not_awaited()
                memory_callbacks["guild"].assert_not_awaited()

    async def test_reserved_state_allows_requests_with_cautious_context(self):
        ai = self.make_ai()
        ai.request_model.return_value = (
            type("Response", (), {
                "text": "اتفضل، هشرحلك.",
                "candidates": [],
                "usage_metadata": None,
            })(),
            [],
        )

        await ai.generate_response(
            "اشرحلي الموضوع ده",
            memories={"personal": [{
                "key": "relationship_state",
                "status": "reserved",
                "improvement_count": 2,
            }]},
        )

        instruction = ai.request_model.await_args.args[3]
        self.assertIn("RESERVED", instruction)
        self.assertIn("2 of 3", instruction)


if __name__ == "__main__":
    unittest.main()

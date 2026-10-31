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

    async def test_pending_conflict_blocks_ordinary_request_before_model(self):
        ai = self.make_ai()

        answer = await ai.generate_response(
            "ممكن تشرحلي بايثون؟",
            memories={"personal": [{
                "key": "relationship_state",
                "status": "awaiting_apology",
                "summary": "خلاف سابق",
            }]},
        )

        self.assertIn("شايل من اللي حصل", answer)
        ai.request_model.assert_not_awaited()

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

        await ai.generate_response(
            "في حريق والحقني بسرعة",
            memories={"personal": [{
                "key": "relationship_state",
                "status": "awaiting_apology",
            }]},
        )

        instruction = ai.request_model.await_args.args[3]
        self.assertIn("urgent safety request", instruction)

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

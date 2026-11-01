import unittest
from unittest.mock import AsyncMock

from services.ai_service import AIService


class NaturalMusicIntentTests(unittest.IsolatedAsyncioTestCase):
    def make_ai(self):
        ai = AIService.__new__(AIService)
        ai.personality = "شخصية فهيم"
        ai.search_service = None
        ai.history_limit = 10
        ai.request_model = AsyncMock(return_value=(
            type("Response", (), {
                "text": "حاضر.",
                "candidates": [],
                "usage_metadata": None,
            })(),
            [],
        ))
        return ai

    def test_music_tool_has_a_bounded_action_schema(self):
        ai = self.make_ai()
        tool = ai.get_music_tool()
        declaration = tool.function_declarations[0]
        schema = declaration.parameters_json_schema

        self.assertEqual(declaration.name, "music_action")
        self.assertEqual(
            set(schema["properties"]["action"]["enum"]),
            {
                "play", "pause", "resume", "skip", "stop", "leave",
                "nowplaying", "queue", "shuffle", "loop", "volume",
            },
        )
        self.assertEqual(schema["required"], ["action"])
        self.assertEqual(
            schema["properties"]["mode"]["enum"],
            ["off", "song", "queue"],
        )

    async def test_natural_music_policy_and_callback_are_passed_to_model(self):
        ai = self.make_ai()
        callback = AsyncMock(return_value={
            "success": True,
            "message": "بدأ التشغيل.",
        })

        await ai.generate_response(
            "نفسي أسمع حاجة هادية",
            music_action_callback=callback,
        )

        ai.request_model.assert_awaited_once()
        instruction = ai.request_model.await_args.args[3]
        self.assertIn("[NATURAL MUSIC CONTROL - STRICT ACTION POLICY]", instruction)
        self.assertIn("Never invent a song title", instruction)
        self.assertIs(
            ai.request_model.await_args.kwargs["music_action_callback"],
            callback,
        )


if __name__ == "__main__":
    unittest.main()

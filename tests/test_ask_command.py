import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import main


class AskCommandTests(unittest.IsolatedAsyncioTestCase):
    def make_interaction(self):
        interaction = SimpleNamespace(
            guild_id=100,
            user=SimpleNamespace(id=200),
            response=SimpleNamespace(
                send_message=AsyncMock()
            ),
            edit_original_response=AsyncMock(),
            followup=SimpleNamespace(
                send=AsyncMock()
            ),
        )
        return interaction

    async def test_successful_ask_passes_memories_and_saves_turn(self):
        interaction = self.make_interaction()

        memory = SimpleNamespace(
            get_history=AsyncMock(return_value=["old message"]),
            get_relevant_user_memories=AsyncMock(
                return_value=[{"key": "job", "value": "developer"}]
            ),
            get_relationship_memory=AsyncMock(
                return_value={
                    "key": "relationship_state",
                    "value": "يوجد خلاف سابق يحتاج إلى تحفظ.",
                }
            ),
            get_relevant_guild_memories=AsyncMock(
                return_value=[{"topic": "agency", "summary": "meeting"}]
            ),
            save_turn=AsyncMock(),
        )

        ai = SimpleNamespace(
            generate_response=AsyncMock(return_value="أهلاً يا سيدي")
        )

        with (
            patch.object(main.bot, "memory_service", memory),
            patch.object(main.bot, "ai_service", ai),
        ):
            await main.ask.callback(interaction, "عامل إيه؟")

        ai.generate_response.assert_awaited_once_with(
            "عامل إيه؟",
            history=["old message"],
            memories={
                "personal": [
                    {"key": "job", "value": "developer"},
                    {
                        "key": "relationship_state",
                        "value": "يوجد خلاف سابق يحتاج إلى تحفظ.",
                    },
                ],
                "shared": [{"topic": "agency", "summary": "meeting"}],
            },
            relationship_event_callback=ANY,
        )

        memory.save_turn.assert_awaited_once_with(
            100, 200, "عامل إيه؟", "أهلاً يا سيدي"
        )
        interaction.edit_original_response.assert_awaited_once_with(
            content="أهلاً يا سيدي"
        )

    async def test_ai_failure_does_not_save_turn(self):
        interaction = self.make_interaction()

        memory = SimpleNamespace(
            get_history=AsyncMock(return_value=[]),
            get_relevant_user_memories=AsyncMock(return_value=[]),
            get_relationship_memory=AsyncMock(return_value=None),
            get_relevant_guild_memories=AsyncMock(return_value=[]),
            save_turn=AsyncMock(),
        )

        ai = SimpleNamespace(
            generate_response=AsyncMock(
                side_effect=RuntimeError("Simulated Gemini failure")
            )
        )

        with (
            patch.object(main.bot, "memory_service", memory),
            patch.object(main.bot, "ai_service", ai),
        ):
            await main.ask.callback(interaction, "اختبار")

        memory.save_turn.assert_not_awaited()
        interaction.edit_original_response.assert_awaited_once_with(
            content="حصلت مشكلة عندي يا سيدي. جرّب تكلمني كمان شوية."
        )

    async def test_dm_request_is_rejected(self):
        interaction = self.make_interaction()
        interaction.guild_id = None

        with patch.object(main.bot, "memory_service") as memory:
            await main.ask.callback(interaction, "اختبار")

        interaction.response.send_message.assert_awaited_once()
        memory.get_history.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import AsyncMock

import main


class MemoryEventCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_personal_memory_is_scoped_to_current_member_and_guild(self):
        memory = type("Memory", (), {})()
        memory.save_user_memory = AsyncMock()

        callbacks = main.make_memory_event_callbacks(
            memory,
            guild_id=100,
            user_id=200,
        )

        result = await callbacks["user"](
            "preferred_language",
            "Egyptian Arabic",
        )

        memory.save_user_memory.assert_awaited_once_with(
            100,
            200,
            "preferred_language",
            "Egyptian Arabic",
        )
        self.assertTrue(result["success"])

    async def test_guild_memory_is_scoped_to_current_guild(self):
        memory = type("Memory", (), {})()
        memory.save_guild_memory = AsyncMock()

        callbacks = main.make_memory_event_callbacks(
            memory,
            guild_id=100,
            user_id=200,
        )

        result = await callbacks["guild"](
            "weekly_meeting",
            "The agency meets every Friday.",
            "community",
            "high",
        )

        memory.save_guild_memory.assert_awaited_once_with(
            100,
            "weekly_meeting",
            "The agency meets every Friday.",
            "community",
            "high",
        )
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()

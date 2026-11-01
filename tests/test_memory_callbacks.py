import unittest
from unittest.mock import AsyncMock

import main
from services.memory_service import MemoryService


class ConversationHistoryRedactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_turn_redacts_credentials_from_user_and_model_text(self):
        service = MemoryService.__new__(MemoryService)
        service.conversations = AsyncMock()

        await service.save_turn(
            100,
            200,
            "My key is AIza" + "A" * 35,
            "Use password=hunter2 to log in.",
        )

        update = service.conversations.update_one.await_args.args[1]
        saved_messages = update["$push"]["history"]["$each"]
        self.assertIn("[REDACTED]", saved_messages[0]["text"])
        self.assertNotIn("AIza", saved_messages[0]["text"])
        self.assertIn("[REDACTED]", saved_messages[1]["text"])
        self.assertNotIn("hunter2", saved_messages[1]["text"])


class MemorySecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_personal_memory_rejects_api_keys_before_database_write(self):
        service = MemoryService.__new__(MemoryService)
        service.user_memories = AsyncMock()

        with self.assertRaisesRegex(ValueError, "Credentials"):
            await service.save_user_memory(
                100, 200, "project_config", "Google key: AIza" + "A" * 35
            )

        service.user_memories.update_one.assert_not_awaited()

    async def test_shared_memory_rejects_passwords_before_database_write(self):
        service = MemoryService.__new__(MemoryService)
        service.guild_memories = AsyncMock()

        with self.assertRaisesRegex(ValueError, "Credentials"):
            await service.save_guild_memory(
                100,
                "deployment",
                "password=hunter2",
                "project",
                "high",
            )

        service.guild_memories.update_one.assert_not_awaited()

    async def test_relationship_memory_rejects_private_keys(self):
        service = MemoryService.__new__(MemoryService)
        service.user_memories = AsyncMock()

        with self.assertRaisesRegex(ValueError, "Credentials"):
            await service.save_relationship_event(
                100,
                200,
                "conflict",
                "-----BEGIN PRIVATE KEY-----",
                "Sensitive detail",
            )

        service.user_memories.find_one.assert_not_awaited()


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

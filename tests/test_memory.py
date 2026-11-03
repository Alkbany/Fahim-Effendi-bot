import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pymongo.errors import DuplicateKeyError

from config import (
    MAX_HISTORY_MESSAGES,
    MAX_MEMORY_CONTEXT_CHARS,
    MEMORY_QUERY_SCAN_LIMIT,
)
from services.ai_service import AIService
from services.memory_service import MemoryService


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents
        self.limit_value = None

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self, length):
        return self.documents[:length]


class MemoryContextTests(unittest.TestCase):
    def setUp(self):
        self.ai = object.__new__(AIService)

    def test_personal_and_shared_memories_are_separated(self):
        context = self.ai.build_memory_context({
            "personal": [{"key": "العمل", "value": "مشروع برمجي"}],
            "shared": [{"topic": "الوكالة", "summary": "اجتماع الجمعة"}],
        })
        self.assertIn("PRIVATE USER MEMORIES", context)
        self.assertIn("SHARED GUILD MEMORIES", context)
        self.assertIn("مشروع برمجي", context)
        self.assertIn("اجتماع الجمعة", context)
        self.assertIn("\n", context)
        self.assertNotIn("\\\\n", context)

    def test_empty_memories_return_empty_context(self):
        self.assertEqual(self.ai.build_memory_context({}), "")

    def test_memory_context_respects_size_limit(self):
        context = self.ai.build_memory_context({
            "personal": [{
                "key": "معلومة",
                "value": "معلومة طويلة " * 2000,
            }],
        })
        self.assertLessEqual(len(context), MAX_MEMORY_CONTEXT_CHARS)


class MemoryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.database = SimpleNamespace(
            user_conversations=SimpleNamespace(
                delete_one=AsyncMock(
                    return_value=SimpleNamespace(deleted_count=1)
                ),
                find_one=AsyncMock(return_value=None),
                update_one=AsyncMock(),
            ),
            guild_memories=SimpleNamespace(
                delete_one=AsyncMock(),
                update_one=AsyncMock(),
            ),
            user_memories=SimpleNamespace(
                find_one=AsyncMock(return_value=None),
                update_one=AsyncMock(),
                delete_one=AsyncMock(),
            ),
        )
        self.memory = MemoryService(self.database)

    async def test_get_history_redacts_and_persists_legacy_credentials(self):
        original_history = [
            {"role": "user", "text": "My API_KEY=AIza" + "A" * 30},
            {"role": "model", "text": "I will keep that private."},
        ]
        self.database.user_conversations.find_one = AsyncMock(
            return_value={"history": original_history}
        )

        history = await self.memory.get_history(100, 200)

        self.assertIn("[REDACTED]", history[0]["text"])
        self.assertNotIn("AIza", history[0]["text"])
        self.database.user_conversations.update_one.assert_awaited_once_with(
            {"guild_id": "100", "user_id": "200"},
            {"$set": {"history": history}},
        )

    async def test_get_history_does_not_write_when_no_credentials_exist(self):
        self.database.user_conversations.find_one = AsyncMock(
            return_value={"history": [
                {"role": "user", "text": "Hello"},
                {"role": "model", "text": "Hi"},
            ]}
        )

        history = await self.memory.get_history(100, 200)

        self.assertEqual(history[0]["text"], "Hello")
        self.database.user_conversations.update_one.assert_not_awaited()

    async def test_legacy_personal_memory_credentials_are_redacted(self):
        cursor = FakeCursor([{
            "guild_id": "100",
            "user_id": "200",
            "key": "api_credential",
            "value": "API_KEY=AIza" + "B" * 30,
        }])
        self.database.user_memories.find = Mock(return_value=cursor)

        result = await self.memory.get_relevant_user_memories(
            100, 200, "credential"
        )

        self.assertEqual(len(result), 1)
        self.assertIn("[REDACTED]", result[0]["value"])
        self.database.user_memories.update_one.assert_awaited_once()

    async def test_legacy_personal_memory_with_secret_in_key_is_deleted(self):
        cursor = FakeCursor([{
            "key": "API_KEY=AIza" + "C" * 30,
            "value": "old secret",
        }])
        self.database.user_memories.find = Mock(return_value=cursor)

        result = await self.memory.get_relevant_user_memories(
            100, 200, "credential"
        )

        self.assertEqual(result, [])
        self.database.user_memories.delete_one.assert_awaited_once_with({
            "guild_id": "100",
            "user_id": "200",
            "key": "API_KEY=AIza" + "C" * 30,
        })

    async def test_legacy_guild_memory_credentials_are_redacted(self):
        cursor = FakeCursor([{
            "guild_id": "100",
            "topic": "project",
            "summary": "password=old-secret",
            "category": "project",
        }])
        self.database.guild_memories.find = Mock(return_value=cursor)

        result = await self.memory.get_relevant_guild_memories(
            100, "project"
        )

        self.assertEqual(len(result), 1)
        self.assertIn("[REDACTED]", result[0]["summary"])
        self.database.guild_memories.update_one.assert_awaited_once()

    async def test_legacy_relationship_credentials_are_redacted(self):
        self.database.user_memories.find_one = AsyncMock(return_value={
            "key": "relationship_state",
            "summary": "password=old-secret",
            "events": [{"type": "conflict", "details": "Bearer old-token"}],
        })

        result = await self.memory.get_relationship_memory(100, 200)

        self.assertIn("[REDACTED]", result["summary"])
        self.assertIn("[REDACTED]", result["events"][0]["details"])
        self.assertEqual(
            self.database.user_memories.update_one.await_count, 2
        )

    async def test_reset_deletes_only_current_user_conversation(self):
        result = await self.memory.reset_conversation(100, 200)
        self.assertTrue(result)
        self.database.user_conversations.delete_one.assert_awaited_once_with({
            "guild_id": "100",
            "user_id": "200",
        })

    async def test_save_turn_retries_duplicate_key_first_write_race(self):
        collection = SimpleNamespace(
            update_one=AsyncMock(side_effect=[
                DuplicateKeyError("concurrent first insert"),
                SimpleNamespace(),
            ])
        )
        self.database.user_conversations = collection
        self.memory.conversations = collection

        await self.memory.save_turn(100, 200, "question", "answer")

        self.assertEqual(collection.update_one.await_count, 2)
        first, second = collection.update_one.call_args_list
        self.assertTrue(first.kwargs["upsert"])
        self.assertFalse(second.kwargs["upsert"])
        self.assertEqual(first.args[0], second.args[0])
        update = first.args[1]
        self.assertEqual(update["$push"]["history"]["$slice"], -MAX_HISTORY_MESSAGES)
        self.assertEqual(
            [item["role"] for item in update["$push"]["history"]["$each"]],
            ["user", "model"],
        )

    async def test_save_guild_memory_retries_duplicate_key_first_write_race(self):
        collection = SimpleNamespace(
            update_one=AsyncMock(side_effect=[
                DuplicateKeyError("concurrent first insert"),
                SimpleNamespace(upserted_id=None),
            ])
        )
        self.database.guild_memories = collection
        self.memory.guild_memories = collection

        await self.memory.save_guild_memory(
            100, "agency project", "project details", "project", "high"
        )

        self.assertEqual(collection.update_one.await_count, 2)
        first, second = collection.update_one.call_args_list
        self.assertTrue(first.kwargs["upsert"])
        self.assertFalse(second.kwargs["upsert"])
        self.assertEqual(first.args[0], second.args[0])

    async def test_save_user_memory_retries_duplicate_key_first_write_race(self):
        collection = SimpleNamespace(
            update_one=AsyncMock(side_effect=[
                DuplicateKeyError("concurrent first insert"),
                SimpleNamespace(),
            ])
        )
        self.database.user_memories = collection
        self.memory.user_memories = collection

        await self.memory.save_user_memory(
            100, 200, "preference", "likes concise answers"
        )

        self.assertEqual(collection.update_one.await_count, 2)
        first, second = collection.update_one.call_args_list
        self.assertTrue(first.kwargs["upsert"])
        self.assertFalse(second.kwargs["upsert"])
        self.assertEqual(first.args[0], second.args[0])

    async def test_save_relationship_event_is_scoped_and_keeps_latest_ten(self):
        self.database.user_memories.update_one = AsyncMock()

        await self.memory.save_relationship_event(
            100,
            200,
            "conflict",
            "إهانة مباشرة لفهيم",
            "يوجد خلاف سابق يحتاج إلى تحفظ.",
        )

        self.database.user_memories.update_one.assert_awaited_once()
        query, update = self.database.user_memories.update_one.call_args.args[:2]

        self.assertEqual(query, {
            "guild_id": "100",
            "user_id": "200",
            "key": "relationship_state",
        })
        self.assertEqual(
            update["$push"]["events"]["$slice"],
            -10,
        )
        self.assertEqual(
            update["$push"]["events"]["$each"][0]["type"],
            "conflict",
        )
        self.assertEqual(
            update["$set"]["summary"],
            "يوجد خلاف سابق يحتاج إلى تحفظ.",
        )
        self.assertTrue(self.database.user_memories.update_one.call_args.kwargs["upsert"])
        self.assertEqual(update["$set"]["status"], "awaiting_apology")
        self.assertEqual(update["$set"]["improvement_count"], 0)

    async def test_apology_without_open_conflict_is_not_applied(self):
        self.database.user_memories.find_one = AsyncMock(return_value={
            "status": "normal",
            "improvement_count": 0,
        })
        result = await self.memory.save_relationship_event(
            100, 200, "apology", "اعتذار عام", "لا يوجد خلاف مفتوح."
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "normal")
        self.database.user_memories.update_one.assert_not_awaited()

    async def test_apology_moves_open_conflict_to_reserved(self):
        self.database.user_memories.find_one = AsyncMock(return_value={
            "status": "awaiting_apology",
            "improvement_count": 0,
        })
        self.database.user_memories.update_one = AsyncMock()
        result = await self.memory.save_relationship_event(
            100, 200, "apology", "اعتذار واضح", "تم الاعتذار."
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "reserved")
        update = self.database.user_memories.update_one.call_args.args[1]
        self.assertEqual(update["$set"]["status"], "reserved")

    async def test_three_improvements_clear_reserved_status(self):
        self.database.user_memories.find_one = AsyncMock(return_value={
            "status": "reserved",
            "improvement_count": 2,
        })
        self.database.user_memories.update_one = AsyncMock()
        result = await self.memory.save_relationship_event(
            100, 200, "improvement", "تحسن واضح", "تحسن السلوك."
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "normal")

    async def test_relationship_update_retries_after_concurrent_write(self):
        self.database.user_memories.find_one = AsyncMock(side_effect=[
            {
                "_id": "relationship-1",
                "status": "reserved",
                "improvement_count": 1,
                "revision": 4,
            },
            {
                "_id": "relationship-1",
                "status": "reserved",
                "improvement_count": 2,
                "revision": 5,
            },
        ])
        self.database.user_memories.update_one = AsyncMock(side_effect=[
            SimpleNamespace(matched_count=0),
            SimpleNamespace(matched_count=1),
        ])

        result = await self.memory.save_relationship_event(
            100, 200, "improvement", "تصرف محترم وواضح", "تحسن السلوك."
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "normal")
        self.assertEqual(result["improvement_count"], 0)
        self.assertEqual(
            self.database.user_memories.update_one.await_count, 2
        )
        first_filter = (
            self.database.user_memories.update_one.call_args_list[0].args[0]
        )
        second_filter = (
            self.database.user_memories.update_one.call_args_list[1].args[0]
        )
        self.assertEqual(first_filter, {
            "_id": "relationship-1",
            "revision": 4,
        })
        self.assertEqual(second_filter, {
            "_id": "relationship-1",
            "revision": 5,
        })

    async def test_first_write_duplicate_key_race_retries_existing_document(self):
        self.database.user_memories.find_one = AsyncMock(side_effect=[
            None,
            {
                "_id": "relationship-1",
                "status": "normal",
                "improvement_count": 0,
                "revision": 1,
            },
        ])
        self.database.user_memories.update_one = AsyncMock(side_effect=[
            DuplicateKeyError("concurrent first insert"),
            SimpleNamespace(matched_count=1),
        ])

        result = await self.memory.save_relationship_event(
            100, 200, "conflict", "إهانة مباشرة", "خلاف مسجل."
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "awaiting_apology")
        self.assertEqual(
            self.database.user_memories.update_one.await_count, 2
        )
        first_call = self.database.user_memories.update_one.call_args_list[0]
        second_call = self.database.user_memories.update_one.call_args_list[1]
        self.assertTrue(first_call.kwargs["upsert"])
        self.assertFalse(second_call.kwargs["upsert"])
        self.assertEqual(second_call.args[0], {
            "_id": "relationship-1",
            "revision": 1,
        })

    async def test_improvement_does_not_clear_unapologized_conflict(self):
        self.database.user_memories.find_one = AsyncMock(return_value={
            "status": "awaiting_apology",
            "improvement_count": 0,
        })
        self.database.user_memories.update_one = AsyncMock()
        result = await self.memory.save_relationship_event(
            100, 200, "improvement", "هدوء في الحديث", "تحسن محدود."
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "awaiting_apology")
        self.database.user_memories.update_one.assert_not_awaited()

    async def test_legacy_relationship_state_is_inferred_from_events(self):
        self.database.user_memories.find_one = AsyncMock(return_value={
            "key": "relationship_state",
            "events": [
                {"type": "conflict"},
                {"type": "apology"},
                {"type": "improvement"},
            ],
        })

        result = await self.memory.get_relationship_memory(100, 200)

        self.assertEqual(result["status"], "reserved")
        self.assertEqual(result["improvement_count"], 1)

    async def test_save_relationship_event_rejects_unknown_event_type(self):
        self.database.user_memories.update_one = AsyncMock()

        with self.assertRaises(ValueError):
            await self.memory.save_relationship_event(
                100,
                200,
                "unknown",
                "تفاصيل الموقف",
                "ملخص العلاقة",
            )

        self.database.user_memories.update_one.assert_not_awaited()

    async def test_relationship_memory_is_always_scoped_to_user_and_guild(self):
        expected = {
            "key": "relationship_state",
            "value": "يوجد خلاف سابق.",
            "status": "normal",
            "improvement_count": 0,
        }
        self.database.user_memories.find_one = AsyncMock(
            return_value=expected
        )

        result = await self.memory.get_relationship_memory(100, 200)

        self.assertEqual(result, expected)
        self.database.user_memories.find_one.assert_awaited_once_with(
            {
                "guild_id": "100",
                "user_id": "200",
                "key": "relationship_state",
            },
            {"_id": 0},
        )

    async def test_personal_memory_query_is_scoped_to_user_and_guild(self):
        cursor = FakeCursor([{
            "guild_id": "100",
            "user_id": "200",
            "key": "المشروع",
            "value": "مشروع برمجي",
        }])
        self.database.user_memories.find = Mock(return_value=cursor)

        result = await self.memory.get_relevant_user_memories(
            100, 200, "المشروع"
        )

        query = self.database.user_memories.find.call_args.args[0]
        self.assertEqual(query["guild_id"], "100")
        self.assertEqual(query["user_id"], "200")
        self.assertEqual(cursor.limit_value, MEMORY_QUERY_SCAN_LIMIT)
        self.assertEqual(len(result), 1)

    async def test_guild_memory_query_is_scoped_to_guild(self):
        cursor = FakeCursor([{
            "guild_id": "100",
            "topic": "مشروع الوكالة",
            "summary": "قرار المشروع",
            "category": "project",
        }])
        self.database.guild_memories.find = Mock(return_value=cursor)

        result = await self.memory.get_relevant_guild_memories(
            100, "مشروع الوكالة"
        )

        query = self.database.guild_memories.find.call_args.args[0]
        self.assertEqual(query["guild_id"], "100")
        self.assertNotIn("user_id", query)
        self.assertEqual(cursor.limit_value, MEMORY_QUERY_SCAN_LIMIT)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()

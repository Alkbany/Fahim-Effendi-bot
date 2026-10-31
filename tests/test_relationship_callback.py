import unittest
from unittest.mock import AsyncMock

import main


class RelationshipCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_saves_event_for_bound_member_only(self):
        memory = type("Memory", (), {})()
        memory.save_relationship_event = AsyncMock(
            return_value={
                "success": False,
                "status": "normal",
                "message": "No unresolved conflict exists.",
            }
        )

        callback = main.make_relationship_event_callback(
            memory,
            guild_id=100,
            user_id=200,
        )

        result = await callback(
            "conflict",
            "إهانة مباشرة لفهيم",
            "يوجد خلاف سابق يحتاج إلى تحفظ.",
        )

        self.assertEqual(
            result,
            {
                "success": False,
                "status": "normal",
                "message": "No unresolved conflict exists.",
            },
        )
        memory.save_relationship_event.assert_awaited_once_with(
            100,
            200,
            "conflict",
            "إهانة مباشرة لفهيم",
            "يوجد خلاف سابق يحتاج إلى تحفظ.",
        )


if __name__ == "__main__":
    unittest.main()

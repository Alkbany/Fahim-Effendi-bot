import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import main


BOT_ID = 999
GUILD_ID = 100
USER_ID = 200
OTHER_CHANNEL_ID = 300


class MessageTriggerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = main.bot
        self.bot._connection.user = SimpleNamespace(
            id=BOT_ID,
            bot=True,
        )

    def make_message(
        self,
        content="hello",
        channel_id=OTHER_CHANNEL_ID,
        author_id=USER_ID,
        author_is_bot=False,
        guild=GUILD_ID,
        reference=None,
    ):
        channel = SimpleNamespace(
            id=channel_id,
            fetch_message=AsyncMock(),
        )
        return SimpleNamespace(
            content=content,
            channel=channel,
            author=SimpleNamespace(
                id=author_id,
                bot=author_is_bot,
            ),
            guild=None if guild is None else SimpleNamespace(id=guild),
            reference=reference,
        )

    async def test_dedicated_channel_triggers_every_human_message(self):
        message = self.make_message(
            channel_id=main.FAHIM_CHANNEL_ID,
            content="صباح الخير",
        )
        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )

    async def test_name_call_triggers_response(self):
        message = self.make_message(content="يا فهيم أفندي عامل إيه؟")
        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )

    async def test_name_call_without_hamza_triggers_response(self):
        message = self.make_message(content="يا فهيم افندي سعر الدولار كام؟")
        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )

    async def test_bot_mention_triggers_response(self):
        message = self.make_message(content=f"<@{BOT_ID}> عامل إيه؟")
        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )

    async def test_nickname_mention_triggers_response(self):
        message = self.make_message(content=f"<@!{BOT_ID}> أخبارك؟")
        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )

    async def test_reply_to_fahim_triggers_response(self):
        reference = SimpleNamespace(
            resolved=SimpleNamespace(
                author=SimpleNamespace(id=BOT_ID)
            )
        )
        message = self.make_message(reference=reference)
        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )

    async def test_reply_to_another_user_does_not_trigger(self):
        reference = SimpleNamespace(
            resolved=SimpleNamespace(
                author=SimpleNamespace(id=555)
            )
        )
        message = self.make_message(reference=reference)
        self.assertFalse(
            await self.bot.should_respond_to_message(message)
        )

    async def test_fetches_unresolved_reply_reference(self):
        reference = SimpleNamespace(
            resolved=None,
            message_id=123,
        )
        message = self.make_message(reference=reference)
        message.channel.fetch_message.return_value = SimpleNamespace(
            author=SimpleNamespace(id=BOT_ID)
        )

        self.assertTrue(
            await self.bot.should_respond_to_message(message)
        )
        message.channel.fetch_message.assert_awaited_once_with(123)

    async def test_listener_does_not_fetch_reference_for_ordinary_message(self):
        message = self.make_message(content="صباح الخير")
        message.reference = SimpleNamespace(
            resolved=None,
            message_id=123,
        )
        process_commands = AsyncMock()
        original = self.bot.process_commands
        self.bot.process_commands = process_commands
        try:
            await self.bot.on_message(message)
        finally:
            self.bot.process_commands = original

        message.channel.fetch_message.assert_not_awaited()
        process_commands.assert_awaited_once_with(message)

    async def test_ordinary_message_elsewhere_does_not_trigger(self):
        message = self.make_message(content="صباح الخير")
        self.assertFalse(
            await self.bot.should_respond_to_message(message)
        )

    async def test_bot_messages_are_ignored(self):
        message = self.make_message(
            channel_id=main.FAHIM_CHANNEL_ID,
            author_is_bot=True,
        )
        self.assertFalse(
            await self.bot.should_respond_to_message(message)
        )

    async def test_direct_messages_are_ignored(self):
        message = self.make_message(guild=None)
        self.assertFalse(
            await self.bot.should_respond_to_message(message)
        )


if __name__ == "__main__":
    unittest.main()

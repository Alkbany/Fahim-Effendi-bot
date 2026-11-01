import asyncio
import logging
import re

import discord
import wavelink
from discord.ext import commands
from contextlib import asynccontextmanager

from config import (\n    DISCORD_TOKEN, FAHIM_CHANNEL_ID, LAVALINK_PASSWORD,\n    LAVALINK_URI, validate_config,\n)
from services.ai_service import AIService
from services.context_service import build_history_question, build_reply_context
from services.database import DatabaseService
from services.memory_service import MemoryService
from services.search_service import SearchService


# =========================
# Logging
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("fahim")


class KeyedLockPool:
    """Serialize work per conversation without blocking other conversations."""

    def __init__(self):
        self._entries = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key):
        async with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                entry = [asyncio.Lock(), 0]
                self._entries[key] = entry
            entry[1] += 1

        lock, _ = entry
        acquired = False
        try:
            await lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                lock.release()

            async with self._guard:
                entry[1] -= 1
                if entry[1] == 0 and self._entries.get(key) is entry:
                    self._entries.pop(key, None)


# =========================
# Discord Helpers
# =========================

def make_relationship_event_callback(memory_service, guild_id, user_id):
    async def record_event(event_type, details, summary):
        return await memory_service.save_relationship_event(
            guild_id,
            user_id,
            event_type,
            details,
            summary,
        )

    return record_event


def make_memory_event_callbacks(memory_service, guild_id, user_id):
    async def save_user_fact(key, value):
        await memory_service.save_user_memory(
            guild_id,
            user_id,
            key,
            value,
        )
        return {"success": True, "message": "Personal memory saved."}

    async def save_guild_fact(topic, summary, category, confidence):
        await memory_service.save_guild_memory(
            guild_id,
            topic,
            summary,
            category,
            confidence,
        )
        return {"success": True, "message": "Shared guild memory saved."}

    return {
        "user": save_user_fact,
        "guild": save_guild_fact,
    }


def split_message(text, limit=1900):
    """Split long responses into Discord-safe messages."""
    chunks = []

    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)

        if split_at < limit // 2:
            split_at = limit

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    if text:
        chunks.append(text)

    return chunks


# =========================
# Fahim Bot
# =========================

class FahimBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.database_service = None
        self.memory_service = None
        self.ai_service = None
        self.search_service = None
        self.music_ready = False
        self.music_node = None
        self.conversation_locks = KeyedLockPool()

    async def setup_hook(self):
        validate_config()

        # Connect to MongoDB
        self.database_service = DatabaseService()
        await self.database_service.connect()

        # Initialize memory service
        self.memory_service = MemoryService(
            self.database_service
        )

        # Initialize search service
        self.search_service = SearchService()

        # Initialize AI service
        self.ai_service = AIService(self.search_service)

        # Register the independent music subsystem before syncing its slash commands.
        await self.load_extension("cogs.music")

        # Music uses Lavalink/Wavelink only; it does not call Gemini.
        try:
            self.music_node = wavelink.Node(
                identifier="fahim-music",
                uri=LAVALINK_URI,
                password=LAVALINK_PASSWORD,
                retries=2,
                client=self,
                inactive_player_timeout=300,
            )
            await wavelink.Pool.connect(
                nodes=[self.music_node],
                client=self,
            )
            self.music_ready = True
            logger.info("Lavalink music node connected.")
        except Exception:
            self.music_ready = False
            self.music_node = None
            logger.warning(
                "Lavalink is unavailable; text chat will continue and music "
                "commands will report that the music service is offline.",
                exc_info=True,
            )

        # Register Discord slash commands
        synced = await self.tree.sync()

        logger.info(
            "Fahim initialized successfully. Synced %s commands.",
            len(synced),
        )

    async def close(self):
        try:
            if self.ai_service:
                try:
                    await self.ai_service.client.aclose()
                except Exception:
                    logger.exception("Failed to close Gemini client.")
        finally:
            try:
                if self.database_service:
                    await self.database_service.close()
            except Exception:
                logger.exception("Failed to close MongoDB connection.")
            finally:
                try:
                    if self.music_node:
                        await wavelink.Pool.close()
                except Exception:
                    logger.exception("Failed to close Lavalink music node.")
                finally:
                    await super().close()


    async def resolve_reference_message(self, message: discord.Message):
        """Resolve a Discord reply once so routing and prompt context use the same message."""
        if not message.reference:
            return None

        reference = message.reference.resolved
        if reference is not None:
            return reference

        try:
            return await message.channel.fetch_message(
                message.reference.message_id
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            logger.warning("Could not resolve replied-to message.")
            return None

    async def should_respond_to_message(
        self,
        message: discord.Message,
        reference_message=None,
    ):
        if message.author.bot or message.guild is None or self.user is None:
            return False

        if message.channel.id == FAHIM_CHANNEL_ID:
            return True

        content = message.content or ""

        if (
            re.search(rf"<@!?{self.user.id}>", content)
            or re.search(r"يا\s+فهيم\s+[اأإ]?فندي", content) is not None
        ):
            return True

        # Preserve direct callers and existing tests: resolve a reply here
        # when the caller has not already resolved it.
        if reference_message is None and message.reference:
            reference_message = await self.resolve_reference_message(message)

        return (
            reference_message is not None
            and reference_message.author.id == self.user.id
        )

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        if self.user is None:
            return

        content = message.content or ""

        reference_message = await self.resolve_reference_message(message)
        if not await self.should_respond_to_message(message, reference_message):
            await self.process_commands(message)
            return

        question = re.sub(
            rf"<@!?{self.user.id}>",
            "",
            content,
        )
        question = re.sub(r"يا\s+فهيم\s+[اأإ]?فندي", "", question).strip()

        if not question and message.reference:
            question = content.strip()

        # Persist only member-authored text; referenced bot text is prompt-only.
        history_question = build_history_question(
            question,
            has_reference=message.reference is not None,
        )

        # A reply to Fahim must carry the exact message being replied to.
        # Recent chat history alone is insufficient when the target is older.
        if (
            reference_message is not None
            and self.user is not None
            and reference_message.author.id == self.user.id
        ):
            question = build_reply_context(
                question,
                reference_message.content or "",
            )

        if not question:
            await message.reply(
                "أؤمر يا سيدي، سامعك.",
                mention_author=False,
            )
            await self.process_commands(message)
            return

        try:
            async with message.channel.typing():
                guild_id = message.guild.id
                user_id = message.author.id

                async with self.conversation_locks.hold((guild_id, user_id)):
                    history = await self.memory_service.get_history(
                        guild_id,
                        user_id,
                    )

                    personal_memories, shared_memories, relationship_memory = await asyncio.gather(
                        self.memory_service.get_relevant_user_memories(
                            guild_id, user_id, question
                        ),
                        self.memory_service.get_relevant_guild_memories(
                            guild_id, question
                        ),
                        self.memory_service.get_relationship_memory(
                            guild_id, user_id
                        ),
                    )

                    if relationship_memory:
                        personal_memories = [
                            item for item in personal_memories
                            if item.get("key") != "relationship_state"
                        ]
                        personal_memories.append(relationship_memory)

                    answer = await self.ai_service.generate_response(
                        question,
                        history=history,
                        memories={
                            "personal": personal_memories,
                            "shared": shared_memories,
                        },
                        relationship_event_callback=make_relationship_event_callback(
                            self.memory_service, guild_id, user_id
                        ),
                        memory_event_callbacks=make_memory_event_callbacks(
                            self.memory_service, guild_id, user_id
                        ),
                    )

                    await self.memory_service.save_turn(
                        guild_id,
                        user_id,
                        history_question,
                        answer,
                    )

            chunks = split_message(answer)

            for index, chunk in enumerate(chunks):
                if index == 0:
                    await message.reply(
                        chunk,
                        mention_author=False,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    await message.channel.send(
                        chunk,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )

        except Exception:
            logger.exception("Error while processing a message.")

            await message.reply(
                "حصلت مشكلة عندي يا سيدي. جرّب تكلمني كمان شوية.",
                mention_author=False,
            )

        await self.process_commands(message)


bot = FahimBot()

# =========================
# Ask Command
# =========================

@bot.tree.command(
    name="ask",
    description="Talk to Fahim Effendi",
)
async def ask(
    interaction: discord.Interaction,
    question: str,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "يا سيدي، كلامنا هنا في الوكالة. ادخل السيرفر وكلمني هناك.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "ثواني يا سيدي، فهيم أفندي بيقلب في الدفاتر... 📚"
    )

    try:
        guild_id = interaction.guild_id
        user_id = interaction.user.id

        async with bot.conversation_locks.hold((guild_id, user_id)):
            # Retrieve this member's conversation history
            history = await bot.memory_service.get_history(
                guild_id,
                user_id,
            )

            # Generate Fahim's response
            personal_memories, shared_memories, relationship_memory = await asyncio.gather(
                bot.memory_service.get_relevant_user_memories(
                    guild_id, user_id, question
                ),
                bot.memory_service.get_relevant_guild_memories(
                    guild_id, question
                ),
                bot.memory_service.get_relationship_memory(
                    guild_id, user_id
                ),
            )

            if relationship_memory:
                personal_memories = [
                    item for item in personal_memories
                    if item.get("key") != "relationship_state"
                ]
                personal_memories.append(relationship_memory)

            answer = await bot.ai_service.generate_response(
                question,
                history=history,
                memories={
                    "personal": personal_memories,
                    "shared": shared_memories,
                },
                relationship_event_callback=make_relationship_event_callback(
                    bot.memory_service, guild_id, user_id
                ),
                memory_event_callbacks=make_memory_event_callbacks(
                    bot.memory_service, guild_id, user_id
                ),
            )

            # Save the conversation
            await bot.memory_service.save_turn(
                guild_id,
                user_id,
                question,
                answer,
            )

        # Replace the temporary message with Fahim's answer
        chunks = split_message(answer)
        await interaction.edit_original_response(
            content=chunks[0],
            allowed_mentions=discord.AllowedMentions.none(),
        )

        for chunk in chunks[1:]:
            await interaction.followup.send(
                chunk,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    except Exception:
        logger.exception("Error while processing /ask")

        await interaction.edit_original_response(
            content="حصلت مشكلة عندي يا سيدي. جرّب تكلمني كمان شوية."
        )


# =========================
# Reset Command
# =========================

@bot.tree.command(
    name="reset",
    description="Reset your conversation with Fahim",
)
async def reset(
    interaction: discord.Interaction,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "الأمر ده متاح داخل الوكالة بس.",
            ephemeral=True,
        )
        return

    try:
        async with bot.conversation_locks.hold(
            (interaction.guild_id, interaction.user.id)
        ):
            deleted = await bot.memory_service.reset_conversation(
                interaction.guild_id,
                interaction.user.id,
            )

        if deleted:
            message = "اتمسح سجل محادثتنا في الوكالة يا سيدي."
        else:
            message = "مفيش عندي سجل محادثة ليك هنا أصلًا."

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

    except Exception:
        logger.exception("Error while processing /reset")

        await interaction.response.send_message(
            "حصلت مشكلة وأنا بنفذ الأمر. حاول تاني بعد شوية.",
            ephemeral=True,
        )


# =========================
# Start Bot
# =========================

if __name__ == "__main__":
    validate_config()
    bot.run(DISCORD_TOKEN)

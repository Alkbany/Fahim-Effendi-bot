import asyncio
import logging
import re

import discord
import wavelink
from discord.ext import commands
from contextlib import asynccontextmanager

from config import (
    DISCORD_TOKEN, FAHIM_CHANNEL_ID, LAVALINK_PASSWORD,
    LAVALINK_URI, validate_config,
)
from services.ai_service import AIService
from services.context_service import build_history_question, build_reply_context
from services.database import DatabaseService
from services.memory_service import MemoryService
from services.search_service import SearchService
from config import MAX_PLAYLIST_TRACKS


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



async def handle_natural_music_request(bot, message, text):
    """Handle clear, direct Egyptian-Arabic music requests without a slash command."""
    if not bot.music_ready or message.guild is None:
        return None

    import re
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    normalized = re.sub(r"^يا\s+فهيم\s+[اأإ]?فندي[،,: ]*", "", normalized)
    normalized = re.sub(r"^<@!?\d+>[،,: ]*", "", normalized)

    player = message.guild.voice_client
    voice_state = getattr(message.author, "voice", None)
    voice_channel = getattr(voice_state, "channel", None)

    # Playback requests: "شغلي ..." / "شغلنا ..." / "شغّل ..."
    play_match = re.match(
        r"^(?:ممكن\s+)?(?:شغل(?:ي|نا)?|شغّل(?:ي|نا)?|شغّل لنا|شغل لنا)\s+(.+)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if play_match:
        query = play_match.group(1).strip(" .،!?؟")
        if not query:
            return None
        if voice_channel is None:
            return "ادخلوا قناة صوتية الأول يا جماعة، مش هشغّل الأغاني في الهوا."
        if player is None:
            try:
                player = await voice_channel.connect(cls=wavelink.Player)
            except Exception:
                logger.exception("Natural music request could not connect to voice.")
                return "مش عارف أدخل القناة الصوتية. راجعوا صلاحياتي."
        elif not isinstance(player, wavelink.Player) or player.channel.id != voice_channel.id:
            return "لازم أكون معاكم في نفس القناة الصوتية."
        try:
            if "open.spotify.com/" in query.lower():
                results = await wavelink.Playable.search(query)
            else:
                results = await wavelink.Playable.search(query, source="ytsearch")
            if not results:
                return "ملقتش أغنية قابلة للتشغيل بالاسم ده."

            logger.info(
                "Music search result | flow=natural | type=%s | playlist_name=%r | count=%s | query=%s",
                type(results).__name__,
                getattr(results, "name", None),
                len(results.tracks) if isinstance(results, wavelink.Playlist) else len(results),
                query,
            )

            is_search_playlist = (
                isinstance(results, wavelink.Playlist)
                and (results.name or "").strip().lower().startswith("search results")
            )
            playlist_name = None
            if isinstance(results, wavelink.Playlist) and not is_search_playlist:
                tracks = results.tracks[:MAX_PLAYLIST_TRACKS]
                playlist_name = results.name or "الأغاني"
            else:
                search_tracks = results.tracks if isinstance(results, wavelink.Playlist) else results
                if not search_tracks:
                    return "القائمة دي مفيهاش حاجة تتشغل."
                tracks = [search_tracks[0]]
                music_cog = bot.get_cog("MusicCog")
                if music_cog is not None:
                    alternatives = list(search_tracks[1:6])
                    music_cog._fallback_tracks[tracks[0].identifier] = alternatives
                    logger.info(
                        "Natural music search stored %s alternatives | query=%s | primary_id=%s",
                        len(alternatives),
                        query,
                        tracks[0].identifier,
                    )

            if not tracks:
                return "القائمة دي مفيهاش حاجة تتشغل."
            await player.queue.put_wait(tracks)
            started = player.current is None
            if started:
                await player.play(player.queue.get())
            if playlist_name:
                return f"حاضر، ضفت {len(tracks)} أغنية من قائمة {playlist_name} للانتظار."
            return f"حاضر، ضفت **{tracks[0].title}** للـQueue." + (" وبدأت محاولة التشغيل." if started else "")
        except Exception:
            logger.exception("Natural music playback failed.")
            return "حصلت مشكلة وأنا بحمّل الأغنية. جرّبوا اسم تاني."

    # Transport controls use explicit phrases to avoid hijacking ordinary chat.
    control_patterns = [
        (r"^(?:وقف|وقفي|وقفلي|وقف لنا) (?:المزيكا|الموسيقى|الأغنية|الأغاني)$", "pause"),
        (r"^(?:كمل|كمّل|استأنف) (?:المزيكا|الموسيقى|الأغنية|الأغاني)$", "resume"),
        (r"^(?:عدي|عدّي|تخطى|تخطّى) (?:الأغنية|التراك|الأغاني)$", "skip"),
        (r"^(?:اقفل|اقفلوا|وقف) (?:المزيكا|الموسيقى) وامسح(?:وا)? الانتظار$", "stop"),
        (r"^(?:اخرج|اطلع) من القناة الصوتية$", "leave"),
    ]
    action = next((name for pattern, name in control_patterns if re.match(pattern, normalized, re.I)), None)
    if action:
        if player is None or not isinstance(player, wavelink.Player):
            return "مفيش تشغيل شغال حاليًا."
        if voice_channel is None or player.channel.id != voice_channel.id:
            return "لازم تكونوا معايا في نفس القناة الصوتية."
        try:
            if action == "pause":
                if player.current is None or player.paused:
                    return "الأغنية مش شغالة دلوقتي."
                await player.pause(True)
                return "وقفتها مؤقتًا."
            if action == "resume":
                if not player.paused:
                    return "هي مش متوقفة مؤقتًا."
                await player.pause(False)
                return "رجّعنا التشغيل."
            if action == "skip":
                if player.current is None:
                    return "مفيش أغنية أعدّيها."
                await player.skip()
                return "عدّيناها."
            if action == "stop":
                player.queue.clear()
                if player.current is not None:
                    await player.stop()
                return "وقفت التشغيل ومسحت الانتظار."
            if action == "leave":
                player.queue.clear()
                await player.disconnect()
                return "خرجت من القناة الصوتية."
        except Exception:
            logger.exception("Natural music control failed.")
            return "حصلت مشكلة وأنا بنفذ أمر الموسيقى."
    return None


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
        self.music_ready_event = asyncio.Event()
        self.music_node = None
        self.music_connect_task = None
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

        # Connect music in the background so an offline Lavalink node never
        # prevents the text bot from starting.
        self.music_connect_task = asyncio.create_task(
            self.connect_music_node()
        )

        # Register Discord slash commands
        synced = await self.tree.sync()

        logger.info(
            "Fahim initialized successfully. Synced %s commands.",
            len(synced),
        )

    async def connect_music_node(self):
        for attempt in range(1, 21):
            node = wavelink.Node(
                identifier="fahim-music",
                uri=LAVALINK_URI,
                password=LAVALINK_PASSWORD,
                retries=3,
                client=self,
                inactive_player_timeout=300,
            )
            try:
                await wavelink.Pool.connect(nodes=[node], client=self)
                # Pool.connect starts the node connection; it does not guarantee
                # that Lavalink has completed its WebSocket handshake yet.
                await asyncio.wait_for(self.music_ready_event.wait(), timeout=15)
                self.music_node = node
                logger.info("Lavalink music node is ready.")
                return
            except Exception:
                self.music_ready = False
                self.music_ready_event.clear()
                logger.warning(
                    "Lavalink connection attempt %s/20 failed.",
                    attempt,
                    exc_info=True,
                )
                try:
                    await wavelink.Pool.close()
                except Exception:
                    pass
                if attempt < 20:
                    await asyncio.sleep(3)

        logger.warning(
            "Lavalink did not become available. Text chat remains active; "
            "music commands will stay offline until the bot reconnects."
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
                    if self.music_connect_task and not self.music_connect_task.done():
                        self.music_connect_task.cancel()
                        await asyncio.gather(
                            self.music_connect_task,
                            return_exceptions=True,
                        )
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


                    if (
                        relationship_memory
                        and relationship_memory.get("status") == "awaiting_apology"
                        and not self.ai_service.is_apology_attempt(question)
                        and not self.ai_service.is_emergency_or_safety_request(question)
                    ):
                        await message.reply(
                            "بعد اللي حصل بينا، مش هقدر أتعامل معاك كأن مفيش حاجة. لما تبقى مستعد تعتذر بوضوح عن اللي صدر منك، نبقى نتكلم.",
                            mention_author=False,
                        )
                        await self.process_commands(message)
                        return

                    music_reply = await handle_natural_music_request(self, message, question)
                    if music_reply is not None:
                        await message.reply(music_reply, mention_author=False)
                        await self.process_commands(message)
                        return

                    if relationship_memory:
                        personal_memories = [
                            item for item in personal_memories
                            if item.get("key") != "relationship_state"
                        ]
                        personal_memories.append(relationship_memory)

                    music_cog = self.get_cog("MusicCog")

                    async def execute_music_action(action, query=None, mode=None, level=None):
                        if music_cog is None:
                            return {"success": False, "message": "نظام الموسيقى مش متاح حاليًا."}
                        return await music_cog.execute_ai_action(
                            message, action, query=query, mode=mode, level=level
                        )

                    answer = await self.ai_service.generate_response(
                        question,
                        history=history,
                        memories={
                            "personal": personal_memories,
                            "shared": shared_memories,
                        },
                        music_action_callback=execute_music_action,
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


            if (
                relationship_memory
                and relationship_memory.get("status") == "awaiting_apology"
                and not bot.ai_service.is_apology_attempt(question)
                and not bot.ai_service.is_emergency_or_safety_request(question)
            ):
                await interaction.edit_original_response(
                    content="بعد اللي حصل بينا، مش هقدر أتعامل معاك كأن مفيش حاجة. لما تبقى مستعد تعتذر بوضوح عن اللي صدر منك، نبقى نتكلم."
                )
                return

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

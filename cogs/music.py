import logging
import re

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from config import LAVALINK_IDENTIFIER, LAVALINK_PASSWORD, LAVALINK_URI, MAX_PLAYLIST_TRACKS

logger = logging.getLogger("fahim.music")


def format_duration(milliseconds, is_stream=False):
    if is_stream:
        return "بث مباشر"
    seconds = max(0, int(milliseconds or 0) // 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class MusicCog(commands.Cog):
    """Music playback through Wavelink connected to an external Lavalink v4 node."""

    def __init__(self, bot):
        self.bot = bot
        self.node_ready = False
        self._locks = {}

    async def cog_load(self):
        self.bot.music_ready = False
        if not (LAVALINK_URI and LAVALINK_PASSWORD):
            logger.warning("Lavalink is not configured. Set LAVALINK_URI and LAVALINK_PASSWORD.")
            return
        try:
            node = wavelink.Node(
                identifier=LAVALINK_IDENTIFIER or "fahim-primary",
                uri=LAVALINK_URI,
                password=LAVALINK_PASSWORD,
                client=self.bot,
                retries=None,
            )
            await wavelink.Pool.connect(nodes=[node], client=self.bot)
            logger.info("Wavelink is connecting to Lavalink node %s.", node.identifier)
        except Exception:
            logger.exception("Could not initialize the Lavalink connection.")

    async def cog_unload(self):
        self.bot.music_ready = False
        try:
            await wavelink.Pool.close()
        except Exception:
            logger.exception("Failed to close Wavelink node pool.")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        self.node_ready = True
        self.bot.music_ready = True
        logger.info("Lavalink node ready | identifier=%s | resumed=%s", payload.node.identifier, payload.resumed)

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: wavelink.NodeDisconnectedEventPayload):
        self.node_ready = False
        self.bot.music_ready = False
        logger.warning("Lavalink node disconnected | identifier=%s", payload.node.identifier)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if player is None or payload.reason != "finished":
            return
        async with self._lock(player.guild.id):
            if player.current is not None or player.queue.is_empty:
                return
            try:
                next_track = player.queue.get()
                await player.play(next_track)
                logger.info("Started queued track | guild=%s | title=%s", player.guild.id, next_track.title)
            except wavelink.QueueEmpty:
                return
            except Exception:
                logger.exception("Failed to start next queued track | guild=%s", player.guild.id)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        logger.error(
            "Lavalink track exception | guild=%s | title=%s | exception=%s",
            payload.player.guild.id if payload.player and payload.player.guild else None,
            getattr(payload.track, "title", "unknown"),
            payload.exception,
        )

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        logger.warning(
            "Lavalink track stuck | guild=%s | title=%s",
            payload.player.guild.id if payload.player and payload.player.guild else None,
            getattr(payload.track, "title", "unknown"),
        )

    def _lock(self, guild_id):
        import asyncio
        return self._locks.setdefault(guild_id, asyncio.Lock())

    def _unavailable_message(self):
        if not LAVALINK_URI or not LAVALINK_PASSWORD:
            return "الموسيقى مش متفعّلة: إعدادات Lavalink الخارجية ناقصة. ضيف LAVALINK_URI وLAVALINK_PASSWORD في Environment Variables."
        return "سيرفر Lavalink مش متصل دلوقتي. راجع حالة الاستضافة والـlogs."

    async def _ensure_player(self, guild, member, *, connect=True):
        if not self.node_ready:
            return None, self._unavailable_message()
        channel = getattr(getattr(member, "voice", None), "channel", None)
        if channel is None:
            return None, "ادخل Voice Channel الأول."
        player = guild.voice_client
        if player is None:
            if not connect:
                return None, "مفيش أغاني شغالة حاليًا."
            try:
                player = await channel.connect(cls=wavelink.Player, timeout=20, reconnect=True)
                await player.set_volume(50)
            except Exception:
                logger.exception("Could not connect Wavelink player to Discord voice.")
                return None, "معرفتش أدخل القناة الصوتية. اتأكد إن عندي Connect وSpeak."
        elif not isinstance(player, wavelink.Player):
            return None, "في اتصال صوتي قديم شغال؛ اخرج من القناة وادخل تاني."
        elif player.channel.id != channel.id:
            return None, "لازم تكون في نفس القناة الصوتية اللي فهيم موجود فيها."
        return player, None

    async def _search(self, query):
        query = query.strip()
        if not query or len(query) > 500:
            return []
        search_query = query if re.match(r"^https?://", query, re.I) or query.lower().startswith("spotify:") else f"ytsearch:{query}"
        results = await wavelink.Playable.search(search_query)
        if not results:
            return []
        if isinstance(results, wavelink.Playlist):
            return list(results.tracks)[:MAX_PLAYLIST_TRACKS]
        return list(results)[:MAX_PLAYLIST_TRACKS]

    async def _enqueue(self, guild, member, query):
        player, error = await self._ensure_player(guild, member)
        if error:
            return {"success": False, "message": error}
        try:
            tracks = await self._search(query)
        except Exception:
            logger.exception("Lavalink search failed.")
            return {"success": False, "message": "البحث فشل من مصدر الصوت. جرّب اسم تاني أو رابط مختلف."}
        if not tracks:
            return {"success": False, "message": "ملقتش نتيجة قابلة للتشغيل للطلب ده."}

        async with self._lock(guild.id):
            started = player.current is None and not player.paused
            first_title = tracks[0].title
            if started:
                first = tracks.pop(0)
                try:
                    await player.play(first)
                except Exception:
                    logger.exception("Lavalink could not start requested track.")
                    return {"success": False, "message": "لقيت الأغنية بس Lavalink معرفش يبدأ تشغيلها."}
            if tracks:
                player.queue.put(tracks, atomic=False)
            queued_count = player.queue.count
            if started and not queued_count:
                message = f"بدأت تشغيل **{first_title}**."
            elif started:
                message = f"بدأت **{first_title}**، واتضافت {len(tracks)} أغنية للانتظار."
            else:
                message = f"اتضافت {len(tracks)} أغنية للانتظار. مكانها: {queued_count}."
        return {"success": True, "message": message, "track": first_title, "started": started, "queued": len(tracks)}

    async def execute_ai_action(self, message, action, query=None, mode=None, level=None):
        guild = getattr(message, "guild", None)
        if guild is None:
            return {"success": False, "message": "أوامر الموسيقى متاحة داخل السيرفر بس."}
        if action == "play":
            if not isinstance(query, str) or not query.strip():
                return {"success": False, "message": "اسم الأغنية مش واضح."}
            return await self._enqueue(guild, message.author, query)

        player, error = await self._ensure_player(guild, message.author, connect=False)
        if error:
            return {"success": False, "message": error}
        current = player.current

        if action == "pause":
            if current is None or player.paused:
                return {"success": False, "message": "مفيش أغنية شغالة أوقفها مؤقتًا."}
            await player.pause(True)
            return {"success": True, "message": "وقفت الأغنية مؤقتًا."}
        if action == "resume":
            if current is None or not player.paused:
                return {"success": False, "message": "الأغنية مش متوقفة مؤقتًا."}
            await player.pause(False)
            return {"success": True, "message": "رجّعت التشغيل."}
        if action == "skip":
            if current is None:
                return {"success": False, "message": "مفيش أغنية شغالة عشان نتخطاها."}
            await player.skip(force=True)
            return {"success": True, "message": f"تخطّينا **{current.title}**."}
        if action == "stop":
            player.queue.reset()
            if current is not None:
                await player.stop(force=True)
            return {"success": True, "message": "وقفت التشغيل ومسحت قائمة الانتظار."}
        if action == "leave":
            player.queue.reset()
            await player.disconnect()
            return {"success": True, "message": "فهيم خرج من القناة الصوتية."}
        if action == "nowplaying":
            if current is None:
                return {"success": False, "message": "مفيش أغنية شغالة حاليًا."}
            return {"success": True, "message": f"الشغالة حاليًا: **{current.title}** — {current.author} ({format_duration(current.length, current.is_stream)})."}
        if action == "queue":
            upcoming = list(player.queue)[:10]
            lines = [f"شغالة حاليًا: {current.title}"] if current else []
            lines.extend(f"{i}. {track.title} — {track.author}" for i, track in enumerate(upcoming, 1))
            return {"success": True, "message": "\n".join(lines) if lines else "قائمة الانتظار فاضية."}
        if action == "shuffle":
            if player.queue.count < 2:
                return {"success": False, "message": "محتاج أغنيتين على الأقل في الانتظار."}
            player.queue.shuffle()
            return {"success": True, "message": "خلطت ترتيب الأغاني اللي جاية."}
        if action == "loop":
            modes = {"off": wavelink.QueueMode.normal, "song": wavelink.QueueMode.loop, "queue": wavelink.QueueMode.loop_all}
            if mode not in modes:
                return {"success": False, "message": "وضع التكرار مش واضح."}
            player.queue.mode = modes[mode]
            player.queue.loaded = current if mode == "song" and current is not None else None
            labels = {"off": "اتقفل", "song": "تكرار الأغنية", "queue": "تكرار القائمة"}
            return {"success": True, "message": f"وضع التكرار: {labels[mode]}."}
        if action == "volume":
            if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 100:
                return {"success": False, "message": "مستوى الصوت لازم يكون من صفر لمية."}
            await player.set_volume(level)
            return {"success": True, "message": f"مستوى الصوت بقى {level}%."}
        return {"success": False, "message": "أمر الموسيقى غير معروف."}

    async def _interaction_action(self, interaction, action, **kwargs):
        if interaction.guild is None:
            return {"success": False, "message": "الأمر ده متاح داخل السيرفر بس."}
        return await self.execute_ai_action(_MessageProxy(interaction.guild, interaction.user), action, **kwargs)

    @app_commands.command(name="play", description="Search for a song or play a URL")
    @app_commands.describe(query="Song name or a supported music URL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)
        result = await self._interaction_action(interaction, "play", query=query)
        await interaction.followup.send(result["message"])

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "pause")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="resume", description="Resume the paused song")
    async def resume(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "resume")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "skip")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "stop")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="leave", description="Disconnect Fahim from voice")
    async def leave(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "leave")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="nowplaying", description="Show the current song")
    async def nowplaying(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "nowplaying")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="queue", description="Show upcoming songs")
    async def queue(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "queue")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, interaction: discord.Interaction):
        result = await self._interaction_action(interaction, "shuffle")
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="loop", description="Set repeat mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Song", value="song"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        result = await self._interaction_action(interaction, "loop", mode=mode.value)
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])

    @app_commands.command(name="volume", description="Set playback volume from 0 to 100")
    @app_commands.describe(level="Volume percentage (0-100)")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
        result = await self._interaction_action(interaction, "volume", level=level)
        await interaction.response.send_message(result["message"], ephemeral=not result["success"])


class _MessageProxy:
    def __init__(self, guild, author):
        self.guild = guild
        self.author = author


async def setup(bot):
    await bot.add_cog(MusicCog(bot))

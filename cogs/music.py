import asyncio
import logging
from typing import Literal

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from config import MAX_PLAYLIST_TRACKS

logger = logging.getLogger("fahim.music")


def format_duration(milliseconds, is_stream=False):
    if is_stream:
        return "بث مباشر"

    seconds = max(0, int(milliseconds or 0) // 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class MusicCog(commands.Cog):
    """Independent Lavalink/Wavelink music player; it does not use Gemini."""

    def __init__(self, bot):
        self.bot = bot
        self._guild_locks = {}
        self._fallback_tracks = {}

    def _lock_for(self, guild_id):
        return self._guild_locks.setdefault(guild_id, asyncio.Lock())

    async def _get_player(self, interaction, *, connect=False):
        if not getattr(self.bot, "music_ready", False):
            return None, "مشغل الموسيقى مش متصل حاليًا. تأكد إن Lavalink شغال."

        if interaction.guild is None:
            return None, "أوامر الموسيقى متاحة داخل السيرفر فقط."

        voice_state = getattr(interaction.user, "voice", None)
        voice_channel = getattr(voice_state, "channel", None)
        if voice_channel is None:
            return None, "ادخل Voice Channel الأول يا سيدي."

        player = interaction.guild.voice_client

        if player is None:
            if not connect:
                return None, "مفيش أغاني شغالة حاليًا."
            try:
                player = await voice_channel.connect(cls=wavelink.Player)
            except Exception:
                logger.exception("Could not connect to the requested voice channel.")
                return None, "معرفتش أدخل القناة الصوتية. راجع صلاحياتي وحاول تاني."

        elif not isinstance(player, wavelink.Player):
            return None, "فيه اتصال صوتي تاني شغال بالفعل."

        elif player.channel.id != voice_channel.id:
            return None, "لازم تكون في نفس القناة الصوتية اللي فهيم موجود فيها."

        player.autoplay = wavelink.AutoPlayMode.disabled
        return player, None

    @staticmethod
    async def _start_next(player):
        if player.current is None and not player.queue.is_empty:
            track = player.queue.get()
            await player.play(track)

    @staticmethod
    def _track_line(track, index=None):
        prefix = f"{index}. " if index is not None else ""
        return f"{prefix}**{track.title}** — {track.author}"

    async def execute_ai_action(self, message, action, query=None, mode=None, level=None):
        """Execute one validated natural-language music action for a Discord member."""
        if not getattr(self.bot, "music_ready", False):
            return {"success": False, "message": "مشغل الموسيقى مش متصل حاليًا. المحادثة العادية ما زالت شغالة."}

        guild = getattr(message, "guild", None)
        if guild is None:
            return {"success": False, "message": "أوامر الموسيقى متاحة داخل السيرفر فقط."}

        voice_state = getattr(message.author, "voice", None)
        voice_channel = getattr(voice_state, "channel", None)
        if voice_channel is None:
            return {"success": False, "message": "لازم العضو يدخل قناة صوتية الأول."}

        player = guild.voice_client
        if action == "play":
            if not isinstance(query, str) or not query.strip() or len(query.strip()) > 500:
                return {"success": False, "message": "اسم الأغنية أو الرابط غير صالح."}
            if player is None:
                try:
                    player = await voice_channel.connect(cls=wavelink.Player)
                except Exception:
                    logger.exception("AI music action could not connect to voice.")
                    return {"success": False, "message": "فهيم معرفش يدخل القناة الصوتية. راجعوا صلاحياته."}
            elif not isinstance(player, wavelink.Player) or player.channel.id != voice_channel.id:
                return {"success": False, "message": "فهيم موجود في قناة صوتية تانية؛ لازم تكونوا في نفس القناة."}

            player.autoplay = wavelink.AutoPlayMode.disabled
            try:
                search_query = query.strip()
                if "open.spotify.com/" in search_query.lower():
                    results = await wavelink.Playable.search(search_query)
                else:
                    results = await wavelink.Playable.search(search_query, source="ytsearch")
                if not results:
                    return {"success": False, "message": "ملقتش نتيجة قابلة للتشغيل للطلب ده."}
                if isinstance(results, wavelink.Playlist):
                    tracks = results.tracks[:MAX_PLAYLIST_TRACKS]
                    playlist_name = results.name or "قائمة الأغاني"
                else:
                    tracks = [results[0]]
                    alternatives = list(results[1:6])
                    self._fallback_tracks[tracks[0].identifier] = alternatives
                    logger.info(
                        "AI music search returned %s tracks; stored %s alternatives | query=%s | primary_id=%s",
                        len(results),
                        len(alternatives),
                        search_query,
                        tracks[0].identifier,
                    )
                    playlist_name = None
                if not tracks:
                    return {"success": False, "message": "القائمة دي مفيهاش أغاني قابلة للتشغيل."}

                async with self._lock_for(guild.id):
                    added = await player.queue.put_wait(tracks)
                    started = player.current is None
                    if started:
                        await self._start_next(player)
                if playlist_name:
                    message_text = f"اتضافت {added} أغنية من قائمة {playlist_name} للانتظار."
                else:
                    message_text = f"اتضافت {tracks[0].title} للانتظار."
                if started:
                    message_text += " وبدأت محاولة التشغيل."
                return {"success": True, "message": message_text, "track": tracks[0].title, "started": started, "queued": added}
            except Exception:
                logger.exception("AI music playback action failed.")
                return {"success": False, "message": "حصلت مشكلة أثناء تحميل الأغنية أو إضافتها للانتظار."}

        if player is None or not isinstance(player, wavelink.Player):
            return {"success": False, "message": "مفيش مشغل موسيقى شغال حاليًا."}
        if player.channel.id != voice_channel.id:
            return {"success": False, "message": "لازم العضو يكون في نفس القناة الصوتية اللي فهيم موجود فيها."}

        try:
            if action == "pause":
                if player.current is None or player.paused:
                    return {"success": False, "message": "مفيش أغنية شغالة أوقفها مؤقتًا."}
                await player.pause(True)
                return {"success": True, "message": "الأغنية اتوقفت مؤقتًا."}
            if action == "resume":
                if not player.paused:
                    return {"success": False, "message": "الأغنية مش متوقفة مؤقتًا."}
                await player.pause(False)
                return {"success": True, "message": "التشغيل رجع."}
            if action == "skip":
                if player.current is None:
                    return {"success": False, "message": "مفيش أغنية شغالة عشان نتخطاها."}
                skipped = await player.skip()
                return {"success": True, "message": "تم تخطي الأغنية.", "track": getattr(skipped, "title", None)}
            if action == "stop":
                player.queue.clear()
                if player.current is not None:
                    await player.stop()
                return {"success": True, "message": "التشغيل اتوقف والانتظار اتمسح."}
            if action == "leave":
                player.queue.clear()
                await player.disconnect()
                return {"success": True, "message": "فهيم خرج من القناة الصوتية."}
            if action == "nowplaying":
                track = player.current
                if track is None:
                    return {"success": False, "message": "مفيش أغنية شغالة حاليًا."}
                return {"success": True, "message": f"الشغالة حاليًا: {track.title} — {track.author} ({format_duration(track.length, track.is_stream)}).", "track": track.title, "artist": track.author}
            if action == "queue":
                upcoming = list(player.queue)[:10]
                current = player.current.title if player.current else None
                if current is None and not upcoming:
                    return {"success": True, "message": "قائمة الانتظار فاضية.", "tracks": []}
                lines = ([f"شغالة حاليًا: {current}"] if current else [])
                lines.extend(f"{index}. {track.title} — {track.author}" for index, track in enumerate(upcoming, 1))
                return {"success": True, "message": "\n".join(lines), "tracks": [track.title for track in upcoming]}
            if action == "shuffle":
                if player.queue.count < 2:
                    return {"success": False, "message": "محتاج أغنيتين على الأقل في الانتظار عشان أخلط ترتيبهم."}
                player.queue.shuffle()
                return {"success": True, "message": "ترتيب الأغاني اللي جاية اتخلط."}
            if action == "loop":
                modes = {"off": wavelink.QueueMode.normal, "song": wavelink.QueueMode.loop, "queue": wavelink.QueueMode.loop_all}
                if mode not in modes:
                    return {"success": False, "message": "وضع التكرار المطلوب مش واضح."}
                player.queue.mode = modes[mode]
                labels = {"off": "اتقفل", "song": "تكرار الأغنية", "queue": "تكرار القائمة"}
                return {"success": True, "message": f"وضع التكرار: {labels[mode]}."}
            if action == "volume":
                if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 100:
                    return {"success": False, "message": "مستوى الصوت لازم يكون رقم من صفر لمية."}
                await player.set_volume(level)
                return {"success": True, "message": f"مستوى الصوت بقى {level}%.", "level": level}
            return {"success": False, "message": "أمر الموسيقى غير معروف."}
        except Exception:
            logger.exception("AI music control action failed | action=%s", action)
            return {"success": False, "message": "حصل خطأ أثناء تنفيذ أمر الموسيقى."}

    @app_commands.command(name="play", description="Play a song or add a link to the music queue")
    @app_commands.describe(query="Song name or a YouTube / Spotify link")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)

        if not query.strip() or len(query) > 500:
            await interaction.followup.send("اكتب اسم الأغنية أو رابط صحيح.")
            return

        player, error = await self._get_player(interaction, connect=True)
        if error:
            await interaction.followup.send(error)
            return

        try:
            if "open.spotify.com/" in query.lower():
                results = await wavelink.Playable.search(query.strip())
            else:
                results = await wavelink.Playable.search(
                    query.strip(),
                    source="ytsearch",
                )
        except wavelink.LavalinkLoadException:
            logger.exception("Music search failed.")
            await interaction.followup.send(
                "المصدر مش قادر يحمّل الطلب دلوقتي. جرّب رابط أو اسم تاني."
            )
            return
        except Exception:
            logger.exception("Unexpected music search error.")
            await interaction.followup.send("حصل خطأ أثناء البحث عن الأغنية.")
            return

        if not results:
            await interaction.followup.send(
                "ملقتش نتيجة قابلة للتشغيل. راجع الرابط أو جرّب اسم الأغنية."
            )
            return

        if isinstance(results, wavelink.Playlist):
            tracks = results.tracks[:MAX_PLAYLIST_TRACKS]
            playlist_name = results.name or "Playlist"
            truncated = len(results.tracks) > len(tracks)
        else:
            tracks = [results[0]]
            alternatives = list(results[1:6])
            self._fallback_tracks[tracks[0].identifier] = alternatives
            logger.info(
                "Slash play search returned %s tracks; stored %s alternatives | query=%s | primary_id=%s",
                len(results),
                len(alternatives),
                query.strip(),
                tracks[0].identifier,
            )
            playlist_name = None
            truncated = False

        if not tracks:
            await interaction.followup.send("القائمة دي مفيهاش أغاني قابلة للتشغيل.")
            return

        async with self._lock_for(interaction.guild_id):
            added = await player.queue.put_wait(tracks)
            started = player.current is None
            if started:
                await self._start_next(player)

        if playlist_name:
            message = (
                f"اتضافت **{added}** أغنية من قائمة **{playlist_name}** للـQueue."
            )
        else:
            message = f"اتضافت **{tracks[0].title}** للـQueue."

        if truncated:
            message += f" (الحد الأقصى للقائمة {MAX_PLAYLIST_TRACKS} أغنية.)"
        if started:
            message += "\nبدأت محاولة التشغيل دلوقتي."
        else:
            message += f"\nمكانها في الانتظار: **{player.queue.count}**."

        await interaction.followup.send(message)

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        if player.current is None or player.paused:
            await interaction.response.send_message("مفيش أغنية شغالة أوقفها.")
            return
        await player.pause(True)
        await interaction.response.send_message("وقفت الأغنية مؤقتًا.")

    @app_commands.command(name="resume", description="Resume the paused song")
    async def resume(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        if not player.paused:
            await interaction.response.send_message("الأغنية مش متوقفة مؤقتًا.")
            return
        await player.pause(False)
        await interaction.response.send_message("كملنا تشغيل.")

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        if player.current is None:
            await interaction.response.send_message("مفيش أغنية شغالة حاليًا.")
            return
        skipped = await player.skip()
        title = skipped.title if skipped else "الأغنية الحالية"
        await interaction.response.send_message(f"تخطّينا **{title}**.")

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        player.queue.clear()
        if player.current is not None:
            await player.stop()
        await interaction.response.send_message("وقفت التشغيل ومسحت الـQueue.")

    @app_commands.command(name="leave", description="Disconnect Fahim from the voice channel")
    async def leave(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        player.queue.clear()
        await player.disconnect()
        await interaction.response.send_message("خرجت من القناة الصوتية.")

    @app_commands.command(name="nowplaying", description="Show the currently playing song")
    async def nowplaying(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        track = player.current
        if track is None:
            await interaction.response.send_message("مفيش أغنية شغالة حاليًا.")
            return

        duration = format_duration(track.length, track.is_stream)
        await interaction.response.send_message(
            f"**دلوقتي شغال:** {track.title}\n"
            f"**الفنان:** {track.author}\n"
            f"**المدة:** {duration}\n"
            f"{track.uri or ''}"
        )

    @app_commands.command(name="queue", description="Show the upcoming songs")
    async def queue(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        upcoming = list(player.queue)[:10]
        if player.current is None and not upcoming:
            await interaction.response.send_message("الـQueue فاضية.")
            return

        lines = []
        if player.current is not None:
            lines.append(f"**شغالة دلوقتي:** {player.current.title}")
        if upcoming:
            lines.append("**الأغاني الجاية:**")
            lines.extend(
                self._track_line(track, index)
                for index, track in enumerate(upcoming, start=1)
            )
        if player.queue.count > len(upcoming):
            lines.append(f"وفيه {player.queue.count - len(upcoming)} أغنية كمان.")

        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="volume", description="Set music volume from 0 to 100")
    @app_commands.describe(level="Volume percentage (0-100)")
    async def volume(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 0, 100],
    ):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await player.set_volume(level)
        await interaction.response.send_message(f"مستوى الصوت بقى **{level}%**.")

    @app_commands.command(name="shuffle", description="Shuffle the upcoming queue")
    async def shuffle(self, interaction: discord.Interaction):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        if player.queue.count < 2:
            await interaction.response.send_message("محتاج أغنيتين على الأقل عشان أخلط الـQueue.")
            return
        player.queue.shuffle()
        await interaction.response.send_message("خلطت ترتيب الأغاني الجاية.")

    @app_commands.command(name="loop", description="Set queue repeat mode")
    @app_commands.describe(mode="Repeat one song, the whole queue, or turn repeat off")
    async def loop(
        self,
        interaction: discord.Interaction,
        mode: Literal["off", "song", "queue"],
    ):
        player, error = await self._get_player(interaction)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        modes = {
            "off": wavelink.QueueMode.normal,
            "song": wavelink.QueueMode.loop,
            "queue": wavelink.QueueMode.loop_all,
        }
        player.queue.mode = modes[mode]
        labels = {"off": "اتقفل", "song": "تكرار الأغنية", "queue": "تكرار القائمة"}
        await interaction.response.send_message(f"وضع التكرار: **{labels[mode]}**.")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        track = payload.track
        if track is not None:
            self._fallback_tracks.pop(track.identifier, None)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if player is None or payload.reason not in {"finished", "stopped"}:
            return

        async with self._lock_for(player.guild.id):
            await self._start_next(player)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        player = payload.player
        if player is None:
            return

        failed_track = payload.track
        logger.warning(
            "Track playback failed in guild %s | track=%s | id=%s | error=%s",
            player.guild.id,
            getattr(failed_track, "title", "unknown"),
            getattr(failed_track, "identifier", "unknown"),
            str(payload.exception),
        )

        alternatives = self._fallback_tracks.pop(failed_track.identifier, [])
        logger.info(
            "Alternative search results available: %s",
            len(alternatives),
        )
        if alternatives:
            next_track = alternatives.pop(0)
            if alternatives:
                self._fallback_tracks[next_track.identifier] = alternatives
            logger.info(
                "Retrying playback with alternative result: %s | id=%s",
                next_track.title,
                next_track.identifier,
            )
            try:
                await player.play(next_track)
                return
            except Exception:
                logger.exception("Could not start an alternative search result.")

        logger.warning(
            "No playable fallback remains for failed track: %s",
            getattr(failed_track, "title", "unknown"),
        )
        if player.current is not None:
            await player.skip()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        self.bot.music_ready = True
        self.bot.music_ready_event.set()
        logger.info("Lavalink node %s is ready.", payload.node.identifier)

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: wavelink.NodeDisconnectedEventPayload):
        self.bot.music_ready = False
        self.bot.music_ready_event.clear()
        logger.warning("Lavalink node %s disconnected.", payload.node.identifier)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        if player.queue.is_empty:
            await player.disconnect()


async def setup(bot):
    await bot.add_cog(MusicCog(bot))

import asyncio
import logging
from collections import deque

import discord
import imageio_ffmpeg
import yt_dlp
from discord import app_commands
from discord.ext import commands

from config import MAX_PLAYLIST_TRACKS

logger = logging.getLogger("fahim.music")

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": False,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}


def format_duration(seconds, is_stream=False):
    if is_stream:
        return "بث مباشر"
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class MusicCog(commands.Cog):
    """Direct Discord voice playback using yt-dlp and bundled FFmpeg."""

    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.locks = {}

    async def cog_load(self):
        self.bot.music_ready = True
        logger.info("Direct yt-dlp music player is ready.")

    def _lock(self, guild_id):
        return self.locks.setdefault(guild_id, asyncio.Lock())

    @staticmethod
    def _extract_sync(query):
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
        if not info:
            return []
        entries = info.get("entries")
        if entries is not None:
            tracks = []
            for entry in entries:
                if not entry:
                    continue
                if entry.get("url") and entry.get("_type") == "url":
                    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                        entry = ydl.extract_info(entry["url"], download=False)
                if entry and entry.get("url"):
                    tracks.append(MusicCog._track_data(entry))
                if len(tracks) >= MAX_PLAYLIST_TRACKS:
                    break
            return tracks
        return [MusicCog._track_data(info)] if info.get("url") else []

    @staticmethod
    def _track_data(info):
        return {
            "title": str(info.get("title") or "Unknown title")[:180],
            "artist": str(info.get("artist") or info.get("uploader") or "Unknown artist")[:120],
            "url": info["url"],
            "webpage_url": info.get("webpage_url") or info.get("original_url") or "",
            "duration": info.get("duration"),
            "is_stream": info.get("is_live", False) or info.get("duration") is None,
        }

    async def _search(self, query):
        query = query.strip()
        if not query or len(query) > 500:
            return []
        if "open.spotify.com/" in query.lower():
            raise ValueError("روابط Spotify مش مدعومة مباشرة. ابعت اسم الأغنية أو رابط YouTube.")
        search = query if query.startswith(("http://", "https://")) else f"ytsearch1:{query}"
        return await asyncio.to_thread(self._extract_sync, search)

    def _state(self, guild_id):
        return self.players.setdefault(guild_id, {
            "queue": deque(),
            "current": None,
            "loop": "off",
            "volume": 0.5,
        })

    async def _ensure_voice(self, guild, member, *, connect=True):
        voice_state = getattr(member, "voice", None)
        channel = getattr(voice_state, "channel", None)
        if channel is None:
            return None, "ادخل Voice Channel الأول."
        voice = guild.voice_client
        if voice is None:
            if not connect:
                return None, "مفيش أغاني شغالة حاليًا."
            try:
                voice = await channel.connect(timeout=20, reconnect=True)
            except Exception:
                logger.exception("Could not connect to Discord voice.")
                return None, "معرفتش أدخل القناة الصوتية. اتأكد إن عندي Connect وSpeak."
        elif voice.channel.id != channel.id:
            return None, "لازم تكون في نفس القناة الصوتية اللي فهيم موجود فيها."
        return voice, None

    def _make_source(self, track, volume):
        before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        audio = discord.FFmpegPCMAudio(
            track["url"],
            executable=FFMPEG_PATH,
            before_options=before,
            options="-vn",
        )
        return discord.PCMVolumeTransformer(audio, volume=volume)

    async def _start_track(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        state = self.players.get(guild_id)
        if guild is None or state is None:
            return
        voice = guild.voice_client
        if voice is None or not state["queue"]:
            state["current"] = None
            return
        track = state["queue"].popleft()
        state["current"] = track
        try:
            source = self._make_source(track, state["volume"])
            loop = self.bot.loop

            def after(error):
                if error:
                    logger.error("FFmpeg playback ended with error: %s", error)
                asyncio.run_coroutine_threadsafe(self._after_track(guild_id), loop)

            voice.play(source, after=after)
            logger.info("Started music | guild=%s | title=%s", guild_id, track["title"])
        except Exception:
            logger.exception("Could not start audio source.")
            state["current"] = None
            await self._start_track(guild_id)

    async def _after_track(self, guild_id):
        async with self._lock(guild_id):
            state = self.players.get(guild_id)
            if state is None:
                return
            finished = state.get("current")
            if finished and state["loop"] == "song":
                state["queue"].appendleft(finished)
            elif finished and state["loop"] == "queue":
                state["queue"].append(finished)
            state["current"] = None
            await self._start_track(guild_id)

    async def _enqueue(self, guild, member, query):
        voice, error = await self._ensure_voice(guild, member)
        if error:
            return {"success": False, "message": error}
        try:
            tracks = await self._search(query)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        except Exception:
            logger.exception("yt-dlp search/extraction failed.")
            return {"success": False, "message": "مش عارف أحمّل الأغنية من المصدر دلوقتي. جرّب اسم أو رابط تاني."}
        if not tracks:
            return {"success": False, "message": "ملقتش نتيجة قابلة للتشغيل للطلب ده."}

        state = self._state(guild.id)
        async with self._lock(guild.id):
            state["queue"].extend(tracks[:MAX_PLAYLIST_TRACKS])
            started = not voice.is_playing() and not voice.is_paused()
            if started:
                await self._start_track(guild.id)
            count = len(state["queue"])
        first = tracks[0]
        if len(tracks) > 1:
            message = f"اتضافت {len(tracks)} أغنية من القائمة للانتظار."
        else:
            message = f"اتضافت **{first['title']}** للانتظار."
        message += " وبدأ التشغيل." if started else f" مكانها في الانتظار: {count}."
        return {
            "success": True,
            "message": message,
            "track": first["title"],
            "started": started,
            "queued": len(tracks),
        }

    async def execute_ai_action(self, message, action, query=None, mode=None, level=None):
        guild = getattr(message, "guild", None)
        if guild is None:
            return {"success": False, "message": "أوامر الموسيقى متاحة داخل السيرفر بس."}
        if action == "play":
            if not isinstance(query, str) or not query.strip():
                return {"success": False, "message": "اسم الأغنية مش واضح."}
            return await self._enqueue(guild, message.author, query)

        voice, error = await self._ensure_voice(guild, message.author, connect=False)
        if error:
            return {"success": False, "message": error}
        state = self._state(guild.id)
        current = state["current"]

        if action == "pause":
            if not voice.is_playing():
                return {"success": False, "message": "مفيش أغنية شغالة أوقفها مؤقتًا."}
            voice.pause()
            return {"success": True, "message": "وقفت الأغنية مؤقتًا."}
        if action == "resume":
            if not voice.is_paused():
                return {"success": False, "message": "الأغنية مش متوقفة مؤقتًا."}
            voice.resume()
            return {"success": True, "message": "رجّعت التشغيل."}
        if action == "skip":
            if current is None:
                return {"success": False, "message": "مفيش أغنية شغالة عشان نتخطاها."}
            voice.stop()
            return {"success": True, "message": f"تخطّينا {current['title']}."}
        if action == "stop":
            state["queue"].clear()
            state["loop"] = "off"
            if voice.is_playing() or voice.is_paused():
                voice.stop()
            state["current"] = None
            return {"success": True, "message": "وقفت التشغيل ومسحت الانتظار."}
        if action == "leave":
            state["queue"].clear()
            state["current"] = None
            await voice.disconnect(force=True)
            self.players.pop(guild.id, None)
            return {"success": True, "message": "فهيم خرج من القناة الصوتية."}
        if action == "nowplaying":
            if current is None:
                return {"success": False, "message": "مفيش أغنية شغالة حاليًا."}
            duration = format_duration(current["duration"], current["is_stream"])
            return {"success": True, "message": f"الشغالة حاليًا: {current['title']} — {current['artist']} ({duration})."}
        if action == "queue":
            upcoming = list(state["queue"])[:10]
            lines = [f"شغالة حاليًا: {current['title']}"] if current else []
            lines.extend(f"{i}. {t['title']} — {t['artist']}" for i, t in enumerate(upcoming, 1))
            return {"success": True, "message": "\n".join(lines) if lines else "قائمة الانتظار فاضية."}
        if action == "shuffle":
            if len(state["queue"]) < 2:
                return {"success": False, "message": "محتاج أغنيتين على الأقل في الانتظار."}
            import random
            items = list(state["queue"])
            random.shuffle(items)
            state["queue"] = deque(items)
            return {"success": True, "message": "خلطت ترتيب الأغاني اللي جاية."}
        if action == "loop":
            if mode not in {"off", "song", "queue"}:
                return {"success": False, "message": "وضع التكرار مش واضح."}
            state["loop"] = mode
            labels = {"off": "اتقفل", "song": "تكرار الأغنية", "queue": "تكرار القائمة"}
            return {"success": True, "message": f"وضع التكرار: {labels[mode]}."}
        if action == "volume":
            if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 100:
                return {"success": False, "message": "مستوى الصوت لازم يكون من صفر لمية."}
            state["volume"] = level / 100
            if current and (voice.is_playing() or voice.is_paused()):
                voice.stop()
                # Restart the current track at its beginning with the new volume.
                state["queue"].appendleft(current)
                state["current"] = None
                if voice.is_paused():
                    voice.resume()
                await self._start_track(guild.id)
            return {"success": True, "message": f"مستوى الصوت بقى {level}%."}
        return {"success": False, "message": "أمر الموسيقى غير معروف."}

    async def _interaction_action(self, interaction, action, **kwargs):
        if interaction.guild is None:
            await interaction.response.send_message("الأمر ده متاح داخل السيرفر بس.", ephemeral=True)
            return None
        result = await self.execute_ai_action(
            _MessageProxy(interaction.guild, interaction.user),
            action,
            **kwargs,
        )
        return result

    @app_commands.command(name="play", description="Search for a song or play a URL")
    @app_commands.describe(query="Song name or a YouTube / SoundCloud link")
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

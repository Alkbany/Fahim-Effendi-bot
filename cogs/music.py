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
            message += "\nبدأ التشغيل دلوقتي."
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

        logger.warning(
            "Track playback failed in guild %s: %s",
            player.guild.id,
            str(payload.exception),
        )
        if player.current is not None:
            await player.skip()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        self.bot.music_ready = True
        logger.info("Lavalink node %s is ready.", payload.node.identifier)

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: wavelink.NodeDisconnectedEventPayload):
        self.bot.music_ready = False
        logger.warning("Lavalink node %s disconnected.", payload.node.identifier)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        if player.queue.is_empty:
            await player.disconnect()


async def setup(bot):
    await bot.add_cog(MusicCog(bot))

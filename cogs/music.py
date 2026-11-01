import asyncio
import logging
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("fahim.music")
MAX_PLAYLIST_TRACKS = 100
YDL_OPTIONS = {"format":"bestaudio/best","quiet":True,"no_warnings":True,"extract_flat":"in_playlist","default_search":"ytsearch","ignoreerrors":True}
FFMPEG_OPTIONS = {"before_options":"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5","options":"-vn"}

def format_duration(seconds, is_stream=False):
    if is_stream: return "بث مباشر"
    seconds=max(0,int(seconds or 0)); h,r=divmod(seconds,3600); m,s=divmod(r,60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

@dataclass
class Track:
    title:str
    url:str
    duration:int=0
    uploader:str="Unknown"
    stream:bool=False

@dataclass
class Player:
    voice:discord.VoiceClient
    queue:deque=field(default_factory=deque)
    current:Track|None=None
    volume:int=70
    loop:str="off"

class MusicCog(commands.Cog):
    """Music playback using discord.py VoiceClient, FFmpeg and yt-dlp."""
    def __init__(self,bot):
        self.bot=bot
        self.players={}

    async def extract(self,query):
        def run():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl: return ydl.extract_info(query,download=False)
        return await asyncio.to_thread(run)

    def make_track(self,info):
        url=info.get("webpage_url") or info.get("original_url")
        if not url and info.get("id"): url=f"https://www.youtube.com/watch?v={info['id']}"
        if not url: return None
        return Track(info.get("title") or "Unknown",url,int(info.get("duration") or 0),info.get("uploader") or info.get("channel") or "Unknown",bool(info.get("is_live")))

    async def search(self,query):
        data=await self.extract(query)
        if not data: return [],None
        if data.get("entries") is not None:
            entries=[x for x in data["entries"] if x][:MAX_PLAYLIST_TRACKS]
            return [t for x in entries if (t:=self.make_track(x))],data.get("title")
        track=self.make_track(data)
        return ([track] if track else []),None

    async def stream_url(self,track):
        data=await self.extract(track.url)
        if data and data.get("entries"): data=next((x for x in data["entries"] if x),None)
        if not data: raise RuntimeError("Unable to resolve audio")
        if data.get("url"): return data["url"]
        raise RuntimeError("No playable audio URL")

    async def connect_player(self,guild,channel):
        voice=guild.voice_client
        if voice is None: voice=await channel.connect()
        elif voice.channel.id!=channel.id: await voice.move_to(channel)
        player=self.players.get(guild.id)
        if player is None or player.voice is not voice:
            player=Player(voice); self.players[guild.id]=player
        return player

    async def play_next(self,guild_id):
        p=self.players.get(guild_id)
        if not p or not p.voice.is_connected() or p.voice.is_playing() or p.voice.is_paused(): return
        if p.loop=="song" and p.current: track=p.current
        elif p.queue:
            if p.loop=="queue" and p.current: p.queue.append(p.current)
            track=p.queue.popleft(); p.current=track
        else: p.current=None; return
        try:
            url=await self.stream_url(track)
            src=discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url,**FFMPEG_OPTIONS),volume=p.volume/100)
            def after(error):
                if error: logger.warning("Playback error in guild %s: %s",guild_id,error)
                self.bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(self.play_next(guild_id)))
            p.voice.play(src,after=after)
        except Exception:
            logger.exception("Failed to play %s",track.title)
            p.current=None
            self.bot.loop.call_soon(asyncio.create_task,self.play_next(guild_id))

    def get_member_channel(self,interaction):
        if interaction.guild is None: return None,"الأوامر دي داخل السيرفر بس."
        channel=getattr(getattr(interaction.user,"voice",None),"channel",None)
        if channel is None: return None,"ادخل قناة صوتية الأول."
        p=self.players.get(interaction.guild_id)
        if p and p.voice.is_connected() and p.voice.channel.id!=channel.id: return None,"لازم تكون في نفس القناة الصوتية."
        return channel,None

    async def enqueue(self,guild,channel,query):
        p=await self.connect_player(guild,channel)
        tracks,playlist=await self.search(query)
        if not tracks: return None,"ملقتش نتيجة قابلة للتشغيل."
        p.queue.extend(tracks)
        started=not p.voice.is_playing() and not p.voice.is_paused()
        await self.play_next(guild.id)
        return (len(tracks),playlist,tracks[0],started),None

    async def execute_ai_action(self,message,action,query=None,mode=None,level=None):
        guild=message.guild
        channel=getattr(getattr(message.author,"voice",None),"channel",None)
        if guild is None or channel is None: return {"success":False,"message":"لازم تدخل قناة صوتية الأول."}
        p=self.players.get(guild.id)
        if action=="play":
            if not isinstance(query,str) or not query.strip(): return {"success":False,"message":"اسم الأغنية غير صالح."}
            try:
                result,error=await self.enqueue(guild,channel,query.strip())
                if error: return {"success":False,"message":error}
                n,playlist,track,started=result
                return {"success":True,"message":f"اتضاف {n} أغنية." + (" وبدأ التشغيل." if started else ""),"track":track.title}
            except Exception:
                logger.exception("AI play failed"); return {"success":False,"message":"حصل خطأ أثناء تحميل الأغنية."}
        if not p or not p.voice.is_connected() or p.voice.channel.id!=channel.id: return {"success":False,"message":"مفيش مشغل شغال في قناتك."}
        try:
            if action=="pause" and p.voice.is_playing(): p.voice.pause(); msg="وقفتها مؤقتًا."
            elif action=="resume" and p.voice.is_paused(): p.voice.resume(); msg="رجّعنا التشغيل."
            elif action=="skip" and (p.voice.is_playing() or p.voice.is_paused()): p.voice.stop(); msg="تم التخطي."
            elif action=="stop":
                p.queue.clear(); p.current=None
                if p.voice.is_playing() or p.voice.is_paused(): p.voice.stop()
                msg="وقفت التشغيل ومسحت الانتظار."
            elif action=="leave":
                p.queue.clear(); await p.voice.disconnect(); self.players.pop(guild.id,None); msg="خرجت من القناة."
            elif action=="nowplaying":
                if not p.current: return {"success":False,"message":"مفيش أغنية شغالة."}
                msg=f"{p.current.title} — {p.current.uploader}"
            elif action=="queue": msg="\n".join([t.title for t in list(p.queue)[:10]]) or "الانتظار فاضي."
            elif action=="shuffle": random.shuffle(p.queue); msg="خلطت ترتيب الانتظار."
            elif action=="loop":
                if mode not in ("off","song","queue"): return {"success":False,"message":"وضع التكرار غير صحيح."}
                p.loop=mode; msg=f"وضع التكرار: {mode}."
            elif action=="volume":
                if not isinstance(level,int) or isinstance(level,bool) or not 0<=level<=100: return {"success":False,"message":"الصوت من صفر لمية."}
                p.volume=level
                if isinstance(p.voice.source,discord.PCMVolumeTransformer): p.voice.source.volume=level/100
                msg=f"الصوت بقى {level}%."
            else: return {"success":False,"message":"الأمر غير متاح أو مفيش أغنية مناسبة."}
            return {"success":True,"message":msg}
        except Exception:
            logger.exception("AI music control failed"); return {"success":False,"message":"حصل خطأ في أمر الموسيقى."}

    @app_commands.command(name="play",description="Play a song or YouTube playlist")
    async def play(self,interaction:discord.Interaction,query:str):
        await interaction.response.defer(thinking=True)
        channel,error=self.get_member_channel(interaction)
        if error: await interaction.followup.send(error); return
        try:
            result,error=await self.enqueue(interaction.guild,channel,query.strip())
            if error: await interaction.followup.send(error); return
            n,playlist,track,started=result
            label=f"{n} أغنية من {playlist}" if playlist else track.title
            await interaction.followup.send(f"اتضافت **{label}** للانتظار." + (" وبدأ التشغيل." if started else ""))
        except Exception:
            logger.exception("Slash play failed"); await interaction.followup.send("حصل خطأ أثناء البحث أو التشغيل.")

    async def control_player(self,interaction):
        channel,error=self.get_member_channel(interaction)
        if error:return None,error
        p=self.players.get(interaction.guild_id)
        if not p or not p.voice.is_connected():return None,"مفيش مشغل شغال."
        return p,None

    @app_commands.command(name="pause",description="Pause playback")
    async def pause(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:i_response=i.response.send_message(e,ephemeral=True); await i_response; return
        if not p.voice.is_playing():await i.response.send_message("مفيش أغنية شغالة.");return
        p.voice.pause();await i.response.send_message("وقفت مؤقتًا.")

    @app_commands.command(name="resume",description="Resume playback")
    async def resume(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        if not p.voice.is_paused():await i.response.send_message("مش متوقفة مؤقتًا.");return
        p.voice.resume();await i.response.send_message("كملنا.")

    @app_commands.command(name="skip",description="Skip current track")
    async def skip(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        if not (p.voice.is_playing() or p.voice.is_paused()):await i.response.send_message("مفيش أغنية شغالة.");return
        p.voice.stop();await i.response.send_message("تخطّينا الأغنية.")

    @app_commands.command(name="stop",description="Stop and clear queue")
    async def stop(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        p.queue.clear();p.current=None
        if p.voice.is_playing() or p.voice.is_paused():p.voice.stop()
        await i.response.send_message("وقفت التشغيل ومسحت الانتظار.")

    @app_commands.command(name="leave",description="Leave voice channel")
    async def leave(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        p.queue.clear();await p.voice.disconnect();self.players.pop(i.guild_id,None)
        await i.response.send_message("خرجت من القناة.")

    @app_commands.command(name="nowplaying",description="Show current track")
    async def nowplaying(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        t=p.current
        if not t:await i.response.send_message("مفيش أغنية شغالة.");return
        await i.response.send_message(f"**{t.title}** — {t.uploader}\n{format_duration(t.duration,t.stream)}\n{t.url}")

    @app_commands.command(name="queue",description="Show music queue")
    async def queue(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        lines=[f"{n}. {t.title}" for n,t in enumerate(list(p.queue)[:10],1)]
        if p.current:lines.insert(0,f"شغالة: {p.current.title}")
        await i.response.send_message("\n".join(lines) or "الانتظار فاضي.")

    @app_commands.command(name="volume",description="Set volume 0-100")
    async def volume(self,i:discord.Interaction,level:app_commands.Range[int,0,100]):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        p.volume=level
        if isinstance(p.voice.source,discord.PCMVolumeTransformer):p.voice.source.volume=level/100
        await i.response.send_message(f"الصوت بقى {level}%.")

    @app_commands.command(name="shuffle",description="Shuffle upcoming tracks")
    async def shuffle(self,i:discord.Interaction):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        random.shuffle(p.queue);await i.response.send_message("خلطت الانتظار.")

    @app_commands.command(name="loop",description="Set repeat mode")
    async def loop(self,i:discord.Interaction,mode:Literal["off","song","queue"]):
        p,e=await self.control_player(i)
        if e:await i.response.send_message(e,ephemeral=True);return
        p.loop=mode;await i.response.send_message(f"وضع التكرار: {mode}.")

async def setup(bot):
    await bot.add_cog(MusicCog(bot))

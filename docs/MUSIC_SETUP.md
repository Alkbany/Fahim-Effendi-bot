# Music subsystem

Fahim uses native `discord.py` voice connections, FFmpeg for audio decoding, and yt-dlp for YouTube search and media extraction. No Lavalink server, Wavelink library, or Docker service is required.

## Requirements
- FFmpeg available on PATH.
- Python dependencies installed from `requirements.txt`.
- Discord bot has Connect and Speak permissions.
- The host permits outbound access to the media source.

## Commands
- `/play` — search for a track or provide a YouTube URL; playlist URLs are supported.
- `/pause`, `/resume`, `/skip`, `/stop`, `/leave`.
- `/nowplaying`, `/queue`, `/volume`, `/shuffle`, `/loop`.

Music is independent of Gemini. Spotify link resolution is not included in this implementation.

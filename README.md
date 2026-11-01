# Fahim Effendi Discord Bot

An Egyptian Arabic Discord companion powered by Gemini, with MongoDB-backed conversation history, personal and shared memories, relationship state, web search, and native Discord voice music playback.

## Features
- Replies in the configured channel, when mentioned, or when members reply to Fahim.
- `/ask` and private `/reset` commands.
- Per-member conversation history and personal memories, plus shared server memories.
- Web search for current information.
- Music playback using discord.py VoiceClient, FFmpeg, and yt-dlp (YouTube search, URLs, and playlists).

## Requirements
- Python 3.12+
- FFmpeg installed and available on PATH
- Discord bot token with Message Content Intent and Voice permissions
- Gemini API key
- MongoDB connection string

## Setup
```bash
git clone <your-repository-url>
cd Fahim-Effendi-bot
python -m venv .venv
```

Activate the environment, then install:
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `DISCORD_TOKEN`, `GEMINI_API_KEY`, and `MONGO_URI`. Optionally set `GEMINI_MODEL` and `FAHIM_CHANNEL_ID`. Never commit secrets.

Install FFmpeg:
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: install an FFmpeg build and add its `bin` directory to PATH.

## Run
```bash
python main.py
```

Music is handled directly by the bot process; there is no separate audio server or Docker dependency. Spotify links are not currently resolved. Use a YouTube URL or search phrase.

## GitHub Codespaces
The devcontainer installs FFmpeg and Python dependencies automatically. Add credentials as Codespaces secrets or in an ignored `.env` file, then run `python main.py`. Codespaces is for development/testing, not 24/7 hosting.

## Tests
```bash
python -m unittest discover -s tests -v
python -m pip check
```

## Project layout
- `main.py` — Discord bot, message handling, slash commands.
- `config.py` — environment and application configuration.
- `cogs/music.py` — native voice playback and music commands.
- `services/` — AI, search, database, memory, and context services.
- `prompts/` — Fahim's personality instructions.
- `tests/` — automated unit tests.
- `scripts/` — useful diagnostic scripts.

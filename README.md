# Fahim Effendi Discord Bot

Fahim is an Egyptian-Arabic Discord companion powered by Gemini, with MongoDB-backed conversation history and long-term memories, live web search, and music playback through an external Lavalink v4 node.

## Features
- Replies in the configured channel, when mentioned, or when a member replies to Fahim.
- /ask and private /reset commands.
- Per-member conversation history and private memories, plus server-scoped shared memories.
- Live web search through DDGS with ordered multi-engine fallback when the primary result is empty or blocked.
- Music playback through Wavelink connected to a separately hosted Lavalink v4 server.
- Fallback Gemini model for eligible transient API failures and empty model responses.
- Automated unit tests and CI on Python 3.12, 3.13, and 3.14.

## Architecture
Discord -> Python bot host (discord.py, Gemini, MongoDB, DDGS, Wavelink)
      -> separate Lavalink v4 host (Java, YouTube Source plugin)

The bot and Lavalink are separate processes and may run on different hosts. The Python bot does not need a local FFmpeg process for this Wavelink architecture.

## Requirements
- Python 3.12 or newer.
- Discord bot token with Message Content Intent and voice permissions.
- Google Gemini API key and MongoDB connection string.
- A Lavalink v4 endpoint and shared password for music (optional; without both settings, music remains disabled).

## Bot setup
```bash
git clone <your-repository-url>
cd Fahim-Effendi-bot
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy .env.example to .env and configure DISCORD_TOKEN, GEMINI_API_KEY, and MONGO_URI. Optional settings include GEMINI_MODEL, GEMINI_FALLBACK_MODEL, FAHIM_CHANNEL_ID, DDGS_BACKEND, DDGS_FALLBACK_BACKENDS, and DDGS_REGION.

For music, set BOTH LAVALINK_URI and LAVALINK_PASSWORD on the bot host. Use the node's public address and assigned port, including http:// or https://. The password must exactly match LAVALINK_SERVER_PASSWORD on the Lavalink host. Never commit secrets.

Run with:
```bash
python main.py
```

## Music deployment
Use lavalink/application.yml as the Lavalink v4 configuration. It declares YouTube Source plugin version 1.18.2, disables Lavalink's deprecated built-in YouTube source, and targets Lavalink 4.2.2 by default for DAVE voice compatibility.

Set on the Lavalink host:
- SERVER_ADDRESS=0.0.0.0
- SERVER_PORT to the port assigned by the hosting panel, if it supplies one.
- LAVALINK_SERVER_PASSWORD to a long, private secret.

Set the matching LAVALINK_URI and LAVALINK_PASSWORD on the Python bot host. The provider must expose the assigned TCP port and allow WebSocket/REST traffic. Use the actual host and port displayed by the provider; do not assume a fixed value.

See docs/MUSIC_SETUP.md for deployment and local Codespaces instructions.

## Tests
```bash
python -m pip check
python -m unittest discover -s tests -v
```

GitHub Actions runs on pushes to the active Lavalink branch and pull requests to main. Unit tests do not replace live checks against Discord, Gemini, MongoDB, and an actual Lavalink node.

## Project layout
- main.py: Discord bot lifecycle, message routing, slash-command sync.
- config.py: environment configuration and validation.
- cogs/music.py: Wavelink music commands and player lifecycle.
- services/: AI, web search, database, memory, and context services.
- lavalink/application.yml: Lavalink v4 and YouTube Source configuration.
- scripts/: local development helpers.
- tests/: automated unit tests.
- docs/: setup, testing, and design notes.

## Important limitations
- Spotify URL resolution is not implemented; the bot reports this rather than passing Spotify links to YouTube search.
- YouTube playback can be affected by source-side restrictions, region availability, or hosting-provider network policy. A successful startup is not proof that audio works.
- Free hosting plans may impose resource, port, sleep, or uptime limitations. Check the current provider panel and terms.

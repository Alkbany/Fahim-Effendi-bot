# Fahim Effendi Discord Bot

An Egyptian Arabic Discord companion powered by Gemini, with MongoDB-backed conversation history, member-scoped relationship state, and web search for questions that need current information.

## Features

- Responds to messages in the configured Fahim channel.
- Responds when mentioned by bot mention or by writing `يا فهيم أفندي`.
- Continues conversations when members reply to one of Fahim's messages.
- Provides the `/ask` slash command and a private `/reset` command for clearing the caller's conversation history.
- Stores conversation history separately for each member in each server.
- Saves durable personal facts privately per member and durable agency facts as shared server memories.
- Keeps relationship state scoped to the specific member and server.
- Uses web search for current information and requires a search before answering detected market-price questions.
- Retries temporary Gemini API failures with a fallback model without repeating searches or relationship side effects.\n- Plays YouTube tracks and playlists through an independent Lavalink music service; Spotify links are supported through the optional LavaSrc integration.

## Requirements

- Python 3.12 or newer.
- A Discord application and bot token.
- A Gemini API key.
- A MongoDB database (MongoDB Atlas is suitable).\n- Docker for the separate Lavalink music service.

## Discord application setup

1. Create an application in the Discord Developer Portal and add a bot.
2. Enable the **Message Content Intent** under Bot → Privileged Gateway Intents. The bot needs it to read ordinary messages and detect mentions.
3. Invite the bot with the `bot` and `applications.commands` scopes.
4. Grant the permissions it needs: View Channels, Send Messages, Read Message History, and Use Application Commands.
5. Copy the bot token. Keep it private.

## Local setup

```bash
git clone <your-repository-url>
cd Fahim-Effendi-bot

python -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

Install dependencies and create your local environment file:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the real values:

- `DISCORD_TOKEN`: token from the Discord Developer Portal.
- `GEMINI_API_KEY`: Gemini API key.
- `MONGO_URI`: MongoDB connection string.
- `GEMINI_MODEL`: optional primary Gemini model override (defaults to `gemini-3.5-flash-lite`; temporary API failures fall back to `gemini-3.6-flash`).
- `FAHIM_CHANNEL_ID`: optional channel ID. If omitted, the current configured default is used.

The application loads `.env` automatically. Never commit `.env` or share its contents.

## Run

```bash
python main.py
```

On startup, Fahim validates configuration, connects to MongoDB, verifies the required indexes, initializes the AI and search services, attempts to connect to the independent Lavalink music node, and syncs Discord slash commands. If Lavalink is offline, chat continues normally and only music commands are unavailable.

## GitHub Codespaces testing

A ready-to-use Codespaces development container is provided in `.devcontainer/`. Open the repository with **Code → Codespaces → Create codespace on main**; dependencies install automatically. Add the required credentials privately as Codespaces secrets or in a local ignored `.env` file. Never commit or share them.

Follow [`docs/CODESPACES_TEST_PLAN.md`](docs/CODESPACES_TEST_PLAN.md) for the full unit and live integration test sequence. Codespaces is for development and testing; it is not the final 24/7 host.

## Tests

Run the full unit-test suite without connecting to Discord, Gemini, or MongoDB:

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the same suite on Python 3.12 and 3.14 for pushes to `main` and pull requests targeting `main`.

## Deployment notes

Run the bot as a **long-running worker/background process**, not as a short-lived request/response web service. Configure the same environment variables in the hosting provider's secret/environment settings, keep the process running, and allow the host's outbound connection to reach MongoDB.

### Docker Compose

With Docker and Docker Compose installed:

1. Copy `.env.example` to `.env` and fill in the real credentials.
2. Build and start Fahim:

```bash
docker compose up -d --build
```

3. Follow the logs:

```bash
docker compose logs -f fahim
```

4. Stop the bot:

```bash
docker compose down
```

The Compose service uses `restart: unless-stopped`, so Docker restarts the worker after a crash or host restart. It does not expose an HTTP port.

Do not put API keys or tokens in source code, screenshots, logs, or deployment files. Restrict MongoDB network access to the deployment host where possible.

## Project layout

- `main.py` — Discord bot, message handling, and slash commands.
- `config.py` — environment and application configuration.
- `services/ai_service.py` — Gemini requests, tool handling, fallback, and response assembly.
- `services/search_service.py` — asynchronous web-search adapter.
- `services/database.py` — MongoDB connection and index initialization.
- `services/memory_service.py` — conversation, personal, guild, and relationship memory operations.
- `prompts/fahim_personality.txt` — Fahim's personality and conversation rules.
- `tests/` — automated unit tests.

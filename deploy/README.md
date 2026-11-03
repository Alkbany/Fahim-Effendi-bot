# Production deployment: Discord bot + Lavalink

Fahim runs as two separate services:

1. Bot service: Python, discord.py, and Wavelink on the bot host.
2. Audio service: Java, Lavalink v4, and YouTube Source plugin on a separate Lavalink-capable host.

They communicate over the Lavalink WebSocket/REST endpoint using a shared password. The bot does not need FFmpeg or yt-dlp for this architecture.

## 1. Bot host

Requirements:
- Python 3.12 or newer.
- Outbound connectivity to Discord, Google Gemini, MongoDB, DDGS search providers, and the Lavalink endpoint.
- Persistent process support if continuous Discord Gateway availability is required.

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Set required environment variables:
- DISCORD_TOKEN
- GEMINI_API_KEY
- MONGO_URI

Optional:
- GEMINI_MODEL
- GEMINI_FALLBACK_MODEL
- FAHIM_CHANNEL_ID
- DDGS_BACKEND and DDGS_REGION

For music, set:
- LAVALINK_URI: public endpoint shown by the audio host, including scheme and port.
- LAVALINK_PASSWORD: same value as LAVALINK_SERVER_PASSWORD on the audio host.
- LAVALINK_IDENTIFIER: optional stable node identifier.

Never commit secrets. Use the hosting provider's secret/environment-variable interface rather than a tracked .env file.

Start the bot with:

```bash
python main.py
```

## 2. Lavalink host

Use lavalink/application.yml from the repository. It declares YouTube Source plugin version 1.18.2 and loads it when Lavalink starts.

Configure the audio host with:
- Java 17 or newer, as required by the Lavalink release.
- SERVER_ADDRESS=0.0.0.0.
- SERVER_PORT equal to the provider's allocated application port when it uses this variable.
- LAVALINK_SERVER_PASSWORD set to a long, unique secret.

Start Lavalink using the host's documented Java command and configured working directory so application.yml is discovered. Ensure the allocated TCP port is exposed publicly and the provider supports WebSocket connections. Do not assume a fixed port or invent a hostname; copy the endpoint from the provider dashboard.

CPU, RAM, JVM heap, storage, process command, and port allocation depend on the host's current plan. Keep JVM heap within the provider's memory limit, leaving headroom for native memory and the operating system. Do not copy resource sizing from a different plan without checking the actual limits.

## 3. Local Linux VM alternative for the bot

On Ubuntu/Debian, install Python and Git:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
git clone <your-repository-url>
cd Fahim-Effendi-bot
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a private environment file from .env.example, set required values, and restrict its permissions:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

A systemd service can run the bot as an unprivileged dedicated user:

```ini
[Unit]
Description=Fahim Effendi Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=fahim
WorkingDirectory=/opt/Fahim-Effendi-bot
ExecStart=/opt/Fahim-Effendi-bot/.venv/bin/python /opt/Fahim-Effendi-bot/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The unit assumes the repository and virtual environment are already owned/readable by the fahim account. Keep Lavalink separate unless the VM is sized to host both processes.

## 4. Operations and security

- Keep secrets in provider-managed environment variables.
- Use a unique Lavalink password and do not expose it in logs.
- Restrict the Lavalink endpoint to the bot host when the provider offers network allowlists.
- Restrict MongoDB network access to the bot host where possible.
- Back up MongoDB independently; application state is stored there.
- Monitor bot and Lavalink logs. A healthy Discord connection does not prove the audio node is healthy.
- Confirm provider sleep, CPU, RAM, storage, port, restart, and uptime rules before relying on a free tier.
- Rotate any credential that has been posted publicly.

## 5. Deployment acceptance

Run unit tests and python -m pip check before deployment. Then verify:
- Discord Gateway connection and command sync.
- Gemini primary and fallback model behavior.
- MongoDB read/write operations.
- Web search returns sources and distinguishes provider failure from genuine zero results.
- Lavalink node-ready event.
- Actual track playback and all player commands in a test voice channel.

Do not call the system production-ready until live integrations pass on the actual hosting providers.

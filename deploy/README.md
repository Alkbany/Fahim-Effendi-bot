# Linux VM deployment (without Docker)

Fahim is a persistent Discord Gateway bot. Run it as a long-lived systemd service on a Linux VM. No Docker or separate audio server is needed.

## Requirements
- Python 3.12+
- FFmpeg installed and available on PATH
- Git
- A Discord bot token, Gemini API key, and MongoDB connection string
- A Linux VM with outbound internet access

No inbound application port is required. Keep the VM firewall closed except for the secure administration method you use.

## Install

1. Connect to the VM securely.
2. Install system packages (Ubuntu/Debian example):

   ```bash
   sudo apt update
   sudo apt install -y git python3 python3-venv python3-pip ffmpeg
   ```

3. Clone the repository:

   ```bash
   git clone <your-repository-url>
   cd Fahim-Effendi-bot
   ```

4. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

5. Create the environment file and set the required secrets:

   ```bash
   cp .env.example .env
   chmod 600 .env
   nano .env
   ```

   Required: `DISCORD_TOKEN`, `GEMINI_API_KEY`, and `MONGO_URI`. Never commit or share this file.

## Run with systemd

Create a dedicated service account and ensure it owns the project directory. Then create `/etc/systemd/system/fahim.service` (replace the path and account with the actual deployment values):

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

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fahim
sudo systemctl status fahim
```

View logs:

```bash
sudo journalctl -u fahim -f
```

## Update

From the project directory:

```bash
git pull --ff-only
. .venv/bin/activate
python -m pip install -r requirements.txt
sudo systemctl restart fahim
```

## Music notes

Music playback runs in the bot process using discord.py VoiceClient, FFmpeg, and yt-dlp. The VM must allow outbound connections to Discord and the media source. Spotify URL resolution is not currently supported.

## Security and availability

- Do not expose an inbound application port; the bot uses outbound connections.
- Restrict MongoDB network access to the VM's outbound IP where possible.
- Keep `.env` private and rotate exposed credentials.
- Free VM capacity and uptime are not guaranteed. Review provider policies and billing limits before relying on a free tier.
- Back up MongoDB independently; bot state is stored there, not in the VM process.

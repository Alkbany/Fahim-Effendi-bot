# Fahim music subsystem (standalone, no Docker)

Fahim uses Wavelink as its Python client and Lavalink as a separate Java process.
Docker and Docker Compose are not used.

## Setup and start in Codespaces

1. Rebuild the existing Codespace once so Java 17 is installed.
2. Add a Codespaces Secret named `LAVALINK_PASSWORD` with a private password.
3. Run the following command in one terminal:

## Start services

Run:

```bash
bash scripts/start_lavalink.sh
```

On first run, the script downloads the latest official Lavalink JAR and the
pinned YouTube plugin directly from their GitHub releases, verifies published
SHA-256 digests when available, then starts Lavalink. No Maven repository or
Docker is involved. Keep this terminal running.

Open a second terminal and start Fahim as usual:

```bash
python main.py
```

Fahim connects to `http://127.0.0.1:2333`. The port is bound to loopback only
and must not be exposed publicly.

## Music commands

- `/play` — search YouTube or submit a YouTube URL.
- `/pause`, `/resume`, `/skip`, `/stop`, `/leave`.
- `/nowplaying`, `/queue`, `/volume`, `/shuffle`, `/loop`.

Natural-language music actions continue to use Fahim's existing AI callback.
Only members in Fahim's voice channel can control the player.

## Important limitation

Changing from yt-dlp in the bot process to Lavalink's YouTube plugin changes the
audio engine and extraction implementation, but it does not guarantee that
YouTube will accept requests from a cloud Codespaces IP. We will test node
startup, search, and actual voice playback before treating the migration as
working.

## Troubleshooting

- If Fahim says the music node is offline, confirm the Lavalink terminal is
  still running and that both processes use the same password.
- If Lavalink fails to start, check Java with `java -version`.
- If YouTube search or playback fails, capture the Lavalink error log; do not
  add browser cookies or account session data.

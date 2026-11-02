# Fahim music subsystem (standalone, no Docker)

Fahim uses Wavelink as its Python client and Lavalink as a separate Java process.
Docker and Docker Compose are not used.

## One-time setup in Codespaces

1. Rebuild the existing Codespace after the devcontainer installs Java 17.
2. Download the latest stable `Lavalink.jar` from the official
   [Lavalink releases](https://github.com/lavalink-devs/Lavalink/releases).
3. Put the file at `lavalink/Lavalink.jar`. Do not commit the JAR.
4. Keep the `lavalink/application.yml` configuration in that same folder.
5. Set the same strong, private `LAVALINK_PASSWORD` in Codespaces Secrets and
   in the Lavalink process environment. If you change it, change both sides.

## Start services

Open one terminal and run:

```bash
./scripts/start_lavalink.sh
```

Wait until Lavalink reports that it has started on port 2333. Keep this terminal
running.

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

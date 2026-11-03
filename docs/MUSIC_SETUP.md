# Music subsystem: Wavelink + Lavalink v4

Fahim's music engine is split into two services:

- Bot host: Python, discord.py, and Wavelink. Wavelink is the client library; it does not download or stream audio itself.
- Audio host: Java and Lavalink v4, with the YouTube Source plugin.

No Docker dependency is required.

## 1. Configure the Lavalink server

Use lavalink/application.yml as the server configuration. It uses SERVER_ADDRESS (default 0.0.0.0) and SERVER_PORT (default 2333), requires LAVALINK_SERVER_PASSWORD, and declares YouTube Source plugin version 1.18.2.

On the Lavalink host, configure:

| Variable | Value |
|---|---|
| SERVER_ADDRESS | 0.0.0.0 |
| SERVER_PORT | The exact port assigned by the provider, if required |
| LAVALINK_SERVER_PASSWORD | A long, private password you generate |

Use the host's documented Java 17+ runtime and startup command. The exact command and port allocation are provider-specific. Make sure the assigned TCP port matches the port Lavalink listens on, and that the provider supports external WebSocket connections. Do not expose the endpoint without a strong password.

## 2. Configure the Python bot host

| Variable | Value |
|---|---|
| LAVALINK_URI | http://HOST:PORT or https://HOST:PORT, using the provider's actual public endpoint |
| LAVALINK_PASSWORD | Exactly the same secret as LAVALINK_SERVER_PASSWORD |
| LAVALINK_IDENTIFIER | Optional; defaults to fahim-primary |

The variable names differ because Lavalink reads LAVALINK_SERVER_PASSWORD, while the Python bot reads LAVALINK_PASSWORD. Keep both out of Git, screenshots, and public logs.

If either bot-side variable is missing, the bot still starts but music is unavailable. This allows normal chat and memory features to start while the audio node is not provisioned.

## 3. Local Codespaces testing

The development container installs Java 17. The launcher defaults to Lavalink 4.2.2, which includes DAVE support for modern Discord voice connections. Add a Codespaces secret named LAVALINK_PASSWORD, then run:

```bash
bash scripts/start_lavalink.sh
```

The script downloads the pinned official Lavalink 4.2.2 JAR by default into the ignored runtime directory. Set LAVALINK_VERSION to intentionally select another compatible release. The YouTube Source plugin is resolved by Lavalink from the dependency declared in application.yml; the script does not download a duplicate plugin JAR.

Keep that terminal running. In a second terminal, configure:

```bash
export LAVALINK_URI=http://127.0.0.1:2333
export LAVALINK_PASSWORD="$LAVALINK_PASSWORD"
python main.py
```

The bot and node must use the same password. Do not expose local port 2333 publicly.

## 4. Commands

- /play — search YouTube or play a supported URL.
- /pause, /resume, /skip, /stop, /leave.
- /nowplaying, /queue, /volume, /shuffle, /loop.
- Fahim also recognises clear natural Egyptian-Arabic play and control requests.

Spotify URL/URI resolution is not implemented. Use a YouTube URL or a song name.

## 5. Release acceptance checklist

Do not mark music as production-ready until all of these pass on the actual provider:

- [ ] Lavalink starts and loads YouTube Source without dependency errors.
- [ ] The provider exposes the advertised host and port.
- [ ] Wavelink logs a node-ready event from the bot host.
- [ ] YouTube text search returns playable tracks.
- [ ] A single track plays in a Discord voice channel.
- [ ] A playlist is capped at the bot's configured maximum.
- [ ] Pause/resume/skip/stop/leave work.
- [ ] Queue, shuffle, loop, and volume work.
- [ ] A temporary node disconnect is logged and the bot recovers after reconnection.
- [ ] No password is printed in logs or committed to Git.

A successful node connection is not enough: verify actual audio in Discord. YouTube may block requests from a hosting IP or change playback requirements; the plugin cannot guarantee every video or region will work.

## Troubleshooting

| Symptom | Check |
|---|---|
| Node stays offline | Public URI, port allocation, shared password, TCP reachability, provider process logs |
| 401/403 | Lavalink password mismatch or provider proxy configuration |
| Connection refused / timeout | Wrong host/port, private-only allocation, firewall, process not listening |
| YouTube search has no results | Plugin loaded, allowSearch, ytsearch prefix, plugin logs |
| Track loads but does not play | Source restrictions, unsupported video, player/voice permissions, Lavalink track exception |
| Bot starts without music | Both bot-side Lavalink variables are configured and node-ready event occurs |

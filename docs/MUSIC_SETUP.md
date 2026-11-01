# Fahim music subsystem

Music is a separate Discord voice feature built with Wavelink and Lavalink. It
does not use Gemini, the AI conversation history, or Gemini API tokens.

## Commands

- /play — search YouTube or submit a YouTube / Spotify URL.
- /pause and /resume — pause and continue playback.
- /skip — skip the current track.
- /stop — stop playback and clear the queue.
- /leave — disconnect from the voice channel.
- /nowplaying and /queue — inspect playback.
- /volume — set volume from 0 to 100.
- /shuffle — shuffle upcoming tracks.
- /loop — turn repeat off, repeat one track, or repeat the queue.

The bot only accepts playback controls from members who are in the same voice
channel as Fahim. Playlists are capped at 100 tracks to keep queue sizes
reasonable.

## Start Lavalink in the existing Codespace

The development container now includes Docker-in-Docker. Rebuild the existing
Codespace container once so that feature is installed; do not create a new
Codespace.

Then start the Lavalink service:

```bash
docker compose up -d lavalink
```

Run the bot from the Codespace terminal as usual:

```bash
python main.py
```

The default local node address is http://127.0.0.1:2333. The node password
defaults to a local development value and is shared by the bot and Lavalink.
For Docker Compose deployment, the bot container uses the internal service
address http://lavalink:2333.

If Lavalink is not running, Fahim's text chat and AI features still start.
Music commands report that the music service is offline instead of preventing
the whole bot from starting.

## Sources

- YouTube search, video links, and playlists use the Lavalink YouTube plugin.
- Spotify track and playlist URLs are resolved by LavaSrc and matched to
  playable audio sources; Spotify itself is not used as a direct Discord audio
  stream.
- Spotify link resolution requires Spotify application client credentials.
  Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET as Codespaces secrets or in
  the ignored local .env file. These are optional; YouTube playback works
  without them.
- The Lavalink node is local to the Codespace / Docker network and its port is
  bound to loopback rather than exposed publicly.

## Basic test sequence

1. Start Lavalink and confirm the bot logs that the music node is ready.
2. Join a voice channel and run /play with a YouTube URL.
3. Run /play with a search phrase and confirm it is queued.
4. Test /pause, /resume, /skip, /queue, /nowplaying, /volume, /shuffle,
   /loop, /stop, and /leave.
5. If Spotify credentials are configured, test one Spotify track URL and one
   playlist URL.
6. Stop Lavalink and confirm that chat still works while music commands report
   the node as offline.

## Natural-language music requests

Fahim can interpret direct music requests through Gemini function calling instead
of relying only on fixed Arabic command patterns. It can play a named track or
a clearly requested mood/genre, pause/resume/skip/stop, leave voice, report the
current track, show the queue, shuffle, set repeat mode, and set volume.

The model must distinguish an actual request to act now from ordinary music
discussion, recommendations, hypotheticals, and memories. It must ask for
clarification when a referenced track is not identifiable, and it may execute
at most one music action per member message. The player result—not the model's
assumption—is the source of truth for whether an action succeeded.

The existing explicit Arabic command patterns remain as a fast path. Other
messages use the same Gemini request already used for the conversation; music
tool calling does not add a separate classification request. As with any
language model interpretation, ambiguous phrasing can still be misunderstood,
so verify behavior with the test cases and real Discord messages before relying
on it in a busy voice channel.

# GitHub Codespaces test plan

## 1. Environment
Open the repository in Codespaces. The devcontainer installs Python 3.13, Java 17, and Python dependencies. Verify:

```bash
python --version
java -version
python -m pip check
```

## 2. Secrets
Configure DISCORD_TOKEN, GEMINI_API_KEY, and MONGO_URI as Codespaces secrets or in an ignored local .env file. Never print or commit secret values.

For local Lavalink testing, also configure LAVALINK_PASSWORD. Do not publish it in logs or screenshots.

## 3. Automated tests
```bash
python -m unittest discover -s tests -v
python -m pip check
```
Resolve failures before live testing.

## 4. Start the bot
```bash
python main.py
```

Confirm MongoDB connects, Discord becomes ready, and slash commands synchronize.

## 5. Discord checks
- [ ] Normal message in the configured Fahim channel.
- [ ] Mention Fahim in another channel.
- [ ] Use /ask and /reset.
- [ ] Reply to an older Fahim message.
- [ ] Verify personal memories remain private to each member.
- [ ] Verify shared memories remain scoped to their server.
- [ ] Ask a question requiring current information and verify live search results and source links.
- [ ] Simulate a search-provider failure; verify Fahim discloses the search limitation rather than claiming there are no results.
- [ ] Send long and rapid messages; check splitting and per-member turn ordering.
- [ ] Simulate an empty primary Gemini response; verify fallback does not repeat a memory write or music action.
- [ ] Check logs for exceptions and ensure no credentials are logged.

## 6. Music checks
For local node testing, start Lavalink in a separate terminal:

```bash
bash scripts/start_lavalink.sh
```

Then configure LAVALINK_URI and LAVALINK_PASSWORD for the bot process, and join a test voice channel:
- [ ] Lavalink loads the YouTube Source plugin without dependency errors.
- [ ] Wavelink logs node-ready.
- [ ] /play with a YouTube URL.
- [ ] /play with a search phrase.
- [ ] Queue a playlist and verify the configured cap.
- [ ] /pause, /resume, /skip, and /stop.
- [ ] /queue, /nowplaying, and /volume.
- [ ] /shuffle, /loop, and /leave.
- [ ] Natural Egyptian-Arabic play and control phrases.
- [ ] Spotify URLs are rejected with a clear unsupported message.
- [ ] Verify audible playback, not only a successful command response.

## 7. Completion gate
Do not call the bot production-ready until unit tests pass, live Discord/Gemini/MongoDB integration checks pass, web search is validated with both results and provider failure cases, music playback is verified in a voice channel, and no credentials appear in repository files or logs.

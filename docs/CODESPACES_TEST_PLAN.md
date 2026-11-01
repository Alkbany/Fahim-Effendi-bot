# GitHub Codespaces test plan

## 1. Environment
Open the repository in Codespaces. The devcontainer installs FFmpeg and the pinned Python dependencies. Verify:
```bash
python --version
ffmpeg -version
python -m pip check
```

## 2. Secrets
Configure `DISCORD_TOKEN`, `GEMINI_API_KEY`, and `MONGO_URI` as Codespaces secrets or in an ignored local `.env` file. Never print or commit secret values.

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
- [ ] Use `/ask` and `/reset`.
- [ ] Reply to an older Fahim message.
- [ ] Verify personal memories remain private to each member.
- [ ] Verify shared memories remain scoped to their server.
- [ ] Ask a question requiring current information and verify search is used.
- [ ] Send long and rapid messages; check splitting and per-member turn ordering.
- [ ] Check logs for exceptions and ensure no credentials are logged.

## 6. Music checks
Use a test server and join a voice channel:
- [ ] `/play` with a YouTube URL.
- [ ] `/play` with a search phrase.
- [ ] Queue a playlist and verify the 100-track cap.
- [ ] `/pause`, `/resume`, `/skip`, and `/stop`.
- [ ] `/queue`, `/nowplaying`, and `/volume`.
- [ ] `/shuffle`, `/loop`, and `/leave`.
- [ ] Natural Egyptian-Arabic play and control phrases.
- [ ] Confirm music playback does not invoke Gemini unnecessarily.

Spotify URL resolution is not currently supported by the native player.

## 7. Completion gate
Do not call the bot production-ready until unit tests pass, live Discord/Gemini/MongoDB integration checks pass, music playback is verified in a voice channel, and no credentials appear in repository files or logs.

# GitHub Codespaces integration test plan

This is the hands-on verification stage before any 24/7 hosting decision. Automated unit tests are necessary, but they do not prove that Discord, Gemini, and MongoDB work together.

## 1. Open the development environment

1. Open the existing Codespace for this repository and pull the latest main branch.
2. The music feature adds Docker-in-Docker to the development container. Rebuild the existing container once so the feature is installed; do not create a second Codespace.
3. Wait for the post-create setup to install the pinned Python dependencies.
4. In the Codespaces terminal, verify the interpreter and dependencies:

   ```bash
   python --version
   python -m pip check
   ```

## 2. Add credentials privately

Fahim needs these environment variables:

- `DISCORD_TOKEN`
- `GEMINI_API_KEY`
- `MONGO_URI`

The existing Codespaces secrets remain in place after rebuilding the container; do not re-enter or print their values. If a local `.env` file is used instead, keep it ignored and never commit it, paste it into a chat, or include it in screenshots or logs. Spotify client credentials are optional and are only needed to resolve Spotify links for music playback.

Do not add secrets to `devcontainer.json`, source files, or GitHub Actions. If a credential is exposed, rotate it.

## 3. Run automated tests first

Run the same test command used by CI:

```bash
python -m unittest discover -s tests -v
```

Then run:

```bash
python -m pip check
```

Resolve every failure before starting the live bot.

## 4. Start Fahim

```bash
python main.py
```

Confirm in the terminal that:
- configuration validation succeeds;
- MongoDB connects and required indexes initialize;
- Discord connects and the bot becomes ready;
- slash commands synchronize without errors.

Keep the Codespace running while testing. Codespaces can stop or time out; this is a development environment, not the final 24/7 host.

## 5. Discord end-to-end checklist

Use a private test server and a test channel. Avoid testing with sensitive personal information.

- [ ] Send a normal message in the configured Fahim channel; verify one reply.
- [ ] Mention Fahim in another channel; verify he responds.
- [ ] Call `/ask`; verify the response edits the initial acknowledgement and handles long responses.
- [ ] Reply to an older Fahim message; verify the referenced message is included in context.
- [ ] Reply to an ordinary member's message; verify Fahim does not respond unless another trigger applies.
- [ ] Use `/reset`; verify only that member's conversation history is cleared.
- [ ] Have two test members converse; verify their histories and personal memories remain separate.
- [ ] Save a personal fact for one test member; verify it is not recalled for another member.
- [ ] Save a shared server fact; verify it is available in the same server but not another server.
- [ ] Ask a question requiring current information; verify the search path runs and the answer distinguishes sourced facts from uncertainty.
- [ ] Send a long prompt; verify message splitting stays within Discord limits.
- [ ] Send two messages quickly from the same member; verify conversation turns do not interleave.
- [ ] Send messages from two different members; verify one slow response does not block the other member.
- [ ] Check logs for exceptions and ensure no API keys, bot tokens, or MongoDB credentials appear.

## 6. Music end-to-end checklist

Start the independent Lavalink node from the existing Codespace:

```bash
docker compose up -d lavalink
docker compose logs -f lavalink
```

Then run Fahim with `python main.py` and confirm the Lavalink node becomes ready.

- [ ] Join a voice channel and run `/play` with a YouTube URL.
- [ ] Run `/play` with a search phrase; verify the track is queued and starts.
- [ ] Test `/pause`, `/resume`, and `/skip`.
- [ ] Test `/queue`, `/nowplaying`, and `/volume`.
- [ ] Test `/shuffle`, `/loop`, `/stop`, and `/leave`.
- [ ] If Spotify credentials are configured, test one Spotify track URL and one playlist URL.
- [ ] Stop Lavalink and verify text chat still works while music commands report the node as offline.

Music playback is independent of Gemini and should not generate Gemini API requests.

## 7. Failure and recovery checks

Perform these only in the test server:

- [ ] Temporarily stop and restart the bot; verify it reconnects and retains database-backed history.
- [ ] Stop MongoDB access or use a deliberately invalid test connection string in a separate test run; verify startup fails clearly without exposing the URI.
- [ ] Test Gemini failure handling with a safe invalid test key or controlled unavailable-model condition; verify the fallback/error path behaves as expected.
- [ ] Verify a restart does not create duplicate bot instances or duplicate replies.

## 8. Completion gate

Do not call the bot production-ready until:
- all unit tests pass in Codespaces;
- all applicable live Discord integration checks pass;
- Gemini and MongoDB work together with the real configuration;
- no secrets appear in repository history or logs;
- any discovered defects are fixed and retested.

Only after this gate should the project move to a separate 24/7 hosting decision.

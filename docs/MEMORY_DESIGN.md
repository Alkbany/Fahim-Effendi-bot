# Fahim's conversation and memory design

Fahim keeps three separate kinds of data in MongoDB. They are scoped to the
small Discord community and are not one unlimited transcript.

## 1. Recent conversation history

Collection: `user_conversations`

- One document per `guild_id` + `user_id`.
- Stores alternating user and assistant messages with timestamps.
- The history array is capped at `MAX_HISTORY_MESSAGES` (currently 50 messages,
  or approximately 15 exchanges). MongoDB's `$slice` removes the oldest
  entries whenever a new turn is saved.
- Gemini receives only the latest `AI_HISTORY_LIMIT` messages (currently 12),
  subject to the per-message and total-character limits in `config.py`.
- This is short-term conversational context, not a lifetime archive.
- Text quoted from a message being replied to is temporary prompt context.
  Only the member's actual message is stored in the transcript.

## 2. Long-term memories

Collections: `user_memories` and `guild_memories`

- Personal memories are scoped by `guild_id` + `user_id`; one member's
  personal memories are never retrieved for another member.
- Shared memories are scoped by `guild_id`; they are available only inside
  that Discord server.
- These collections store selected durable facts, not every message.
- The AI is instructed to save useful facts only when explicitly requested
  or when their lasting value is clear. Temporary chatter should stay in the
  recent conversation history.
- Relationship state is a separate personal-memory record for each member.

## 3. Reset behavior

`/reset` deletes only the calling member's recent conversation document for
the current server. It does not delete personal memories, shared server
memories, or relationship state.

## Current limits

The limits live in `config.py`; update the tests when changing them. The bot
does not currently create an AI-generated summary of discarded history. Once
messages fall outside the rolling 30-message window, they are no longer
available as conversation history unless a durable fact was separately saved
as a long-term memory.

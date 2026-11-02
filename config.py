import os

from dotenv import load_dotenv


load_dotenv()


# API Keys and Secrets
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")


# Gemini Configuration
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)


# MongoDB Configuration
MONGO_DATABASE = "fahim_database"



def validate_config():
    required = {
        "DISCORD_TOKEN": DISCORD_TOKEN,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "MONGO_URI": MONGO_URI,
    }

    missing = [
        name for name, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            f"Missing environment variables: {', '.join(missing)}"
        )
# Memory Collections
USER_CONVERSATIONS_COLLECTION = "user_conversations"
GUILD_MEMORIES_COLLECTION = "guild_memories"
USER_MEMORIES_COLLECTION = "user_memories"
MAX_HISTORY_MESSAGES = 30
AI_HISTORY_LIMIT = 6
MAX_HISTORY_MESSAGE_CHARS = 900
MAX_HISTORY_CONTEXT_CHARS = 3500


# Memory safety and context limits
MAX_PERSONAL_MEMORIES = 5
MAX_GUILD_MEMORIES = 3
MAX_MEMORY_TEXT_CHARS = 1000
MAX_MEMORY_CONTEXT_CHARS = 4000


# Standalone Lavalink music node (Java process; no Docker).
LAVALINK_URI = os.getenv("LAVALINK_URI", "http://127.0.0.1:2333")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "change-this-local-password")
MAX_PLAYLIST_TRACKS = 100

# Dedicated channel for Fahim
FAHIM_CHANNEL_ID = int(
    os.getenv("FAHIM_CHANNEL_ID", "1320069245232742588")
)

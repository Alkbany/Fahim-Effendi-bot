import os

from dotenv import load_dotenv


load_dotenv()


# API Keys and Secrets
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")


# Gemini Configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")


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
MAX_HISTORY_MESSAGES = 50
AI_HISTORY_LIMIT = 12
MAX_HISTORY_MESSAGE_CHARS = 1200
MAX_HISTORY_CONTEXT_CHARS = 6000


# Memory safety and context limits
MAX_PERSONAL_MEMORIES = 6
MAX_GUILD_MEMORIES = 4
MEMORY_QUERY_SCAN_LIMIT = 40
MAX_MEMORY_TEXT_CHARS = 1000
MAX_MEMORY_CONTEXT_CHARS = 3500


# External Lavalink v4 node used by the Wavelink client.
LAVALINK_URI = os.getenv("LAVALINK_URI")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD")
LAVALINK_IDENTIFIER = os.getenv("LAVALINK_IDENTIFIER", "fahim-primary")
MAX_PLAYLIST_TRACKS = 100

# Dedicated channel for Fahim
try:
    FAHIM_CHANNEL_ID = int(os.getenv("FAHIM_CHANNEL_ID", "1320069245232742588"))
except ValueError as error:
    raise RuntimeError("FAHIM_CHANNEL_ID must be a valid Discord channel ID.") from error

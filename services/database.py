import logging

from pymongo import AsyncMongoClient

from config import (
    MONGO_URI,
    MONGO_DATABASE,
    USER_CONVERSATIONS_COLLECTION,
    GUILD_MEMORIES_COLLECTION,
    USER_MEMORIES_COLLECTION,
)

logger = logging.getLogger("fahim.database")


class DatabaseService:

    def __init__(self):
        self.client = None
        self.database = None

        self.user_conversations = None
        self.guild_memories = None
        self.user_memories = None

    async def connect(self):
        if self.client is not None:
            raise RuntimeError("Database is already initialized.")

        self.client = AsyncMongoClient(MONGO_URI)

        try:
            await self.client.admin.command("ping")

            self.database = self.client[MONGO_DATABASE]

            self.user_conversations = self.database[
                USER_CONVERSATIONS_COLLECTION
            ]

            self.guild_memories = self.database[
                GUILD_MEMORIES_COLLECTION
            ]

            self.user_memories = self.database[
                USER_MEMORIES_COLLECTION
            ]

            await self.user_conversations.create_index(
                [("guild_id", 1), ("user_id", 1)],
                unique=True,
                name="guild_user_conversation",
            )

            await self.user_memories.create_index(
                [
                    ("guild_id", 1),
                    ("user_id", 1),
                    ("key", 1),
                ],
                unique=True,
                name="guild_user_memory_key",
            )

            existing_indexes = (
                await self.guild_memories.index_information()
            )

            if "guild_topic_search" in existing_indexes:
                await self.guild_memories.drop_index(
                    "guild_topic_search"
                )

            await self.guild_memories.create_index(
                [("guild_id", 1), ("topic", 1)],
                unique=True,
                name="guild_topic_unique",
            )

            logger.info("MongoDB connected and indexes verified.")

        except Exception:
            logger.exception("MongoDB initialization failed.")
            await self.close()
            raise

    async def close(self):
        if self.client is not None:
            await self.client.close()

        self.client = None
        self.database = None
        self.user_conversations = None
        self.guild_memories = None
        self.user_memories = None

        logger.info("MongoDB connection closed.")

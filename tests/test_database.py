import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.database import DatabaseService


class DatabaseServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, existing_guild_indexes=None, ping_error=None):
        client = MagicMock()
        client.admin.command = AsyncMock(side_effect=ping_error)

        database = MagicMock()
        collections = {
            "user_conversations": MagicMock(),
            "guild_memories": MagicMock(),
            "user_memories": MagicMock(),
        }

        client.__getitem__.return_value = database
        database.__getitem__.side_effect = collections.__getitem__

        for collection in collections.values():
            collection.create_index = AsyncMock()

        collections["guild_memories"].index_information = AsyncMock(
            return_value=existing_guild_indexes or {}
        )
        collections["guild_memories"].drop_index = AsyncMock()
        client.close = AsyncMock()

        return client, collections

    async def test_connect_creates_required_indexes(self):
        client, collections = self.make_client()

        with patch(
            "services.database.AsyncMongoClient",
            return_value=client,
        ) as client_factory:
            service = DatabaseService()
            await service.connect()

        client_factory.assert_called_once()
        client.admin.command.assert_awaited_once_with("ping")
        collections["user_conversations"].create_index.assert_awaited_once()
        collections["user_memories"].create_index.assert_awaited_once()
        collections["guild_memories"].create_index.assert_awaited_once()
        collections["guild_memories"].drop_index.assert_not_awaited()

        self.assertIs(service.client, client)
        self.assertIsNotNone(service.database)

    async def test_connect_replaces_legacy_guild_search_index(self):
        client, collections = self.make_client(
            existing_guild_indexes={"guild_topic_search": {}}
        )

        with patch("services.database.AsyncMongoClient", return_value=client):
            service = DatabaseService()
            await service.connect()

        collections["guild_memories"].drop_index.assert_awaited_once_with(
            "guild_topic_search"
        )
        collections["guild_memories"].create_index.assert_awaited_once()

    async def test_failed_connection_closes_client_and_resets_state(self):
        client, _ = self.make_client(
            ping_error=RuntimeError("MongoDB unavailable")
        )

        with patch("services.database.AsyncMongoClient", return_value=client):
            service = DatabaseService()
            with self.assertRaisesRegex(RuntimeError, "MongoDB unavailable"):
                await service.connect()

        client.close.assert_awaited_once()
        self.assertIsNone(service.client)
        self.assertIsNone(service.database)

    async def test_close_awaits_client_and_clears_references(self):
        client, _ = self.make_client()

        with patch("services.database.AsyncMongoClient", return_value=client):
            service = DatabaseService()
            await service.connect()
            await service.close()

        client.close.assert_awaited_once()
        self.assertIsNone(service.client)
        self.assertIsNone(service.database)
        self.assertIsNone(service.user_conversations)
        self.assertIsNone(service.guild_memories)
        self.assertIsNone(service.user_memories)


if __name__ == "__main__":
    unittest.main()

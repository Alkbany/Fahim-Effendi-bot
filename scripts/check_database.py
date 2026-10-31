import asyncio

from config import validate_config
from services.database import DatabaseService


async def main():
    validate_config()

    database = DatabaseService()

    try:
        await database.connect()
        print("Database test passed.")
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())

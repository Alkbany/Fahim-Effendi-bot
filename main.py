
import os
import time
import discord

from discord.ext import commands
from google import genai
from google.genai import types
from motor.motor_asyncio import AsyncIOMotorClient


# =========================
# Configuration
# =========================

MODEL_NAME = "gemini-3.8-flash"

SYSTEM_INSTRUCTION = """
You are Fahim Effendi, a helpful and friendly Discord assistant.
Reply naturally, clearly, and concisely.
"""


# =========================
# Discord Bot
# =========================

class FahimBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents
        )

        self.mongo_client = None
        self.db = None
        self.chats_collection = None
        self.ai_client = None

    async def setup_hook(self):

        # MongoDB
        mongo_uri = os.getenv("MONGO_URI")

        if not mongo_uri:
            raise ValueError("MONGO_URI is missing!")

        self.mongo_client = AsyncIOMotorClient(mongo_uri)

        self.db = self.mongo_client["fahim_database"]
        self.chats_collection = self.db["user_chats"]

        # Gemini Async Client
        gemini_key = os.getenv("GEMINI_API_KEY")

        if not gemini_key:
            raise ValueError("GEMINI_API_KEY is missing!")

        self.ai_client = genai.Client(
            api_key=gemini_key
        ).aio

        # Sync Discord commands
        await self.tree.sync()

        print("Fahim Effendi is online and ready!")

    async def close(self):

        if self.mongo_client:
            self.mongo_client.close()

        await super().close()


bot = FahimBot()


# =========================
# Ask Command
# =========================

@bot.tree.command(
    name="ask",
    description="Ask Fahim Effendi"
)
async def ask(
    interaction: discord.Interaction,
    question: str
):

    await interaction.response.defer()

    user_id = str(interaction.user.id)

    try:

        # 1. Read history from MongoDB
        start = time.perf_counter()

        user_data = await bot.chats_collection.find_one(
            {"_id": user_id}
        )

        db_history = (
            user_data.get("history", [])
            if user_data
            else []
        )

        db_read_time = time.perf_counter() - start

        # 2. Convert history to Gemini format
        gemini_history = []

        for msg in db_history:

            gemini_history.append(
                types.Content(
                    role=msg["role"],
                    parts=[
                        types.Part.from_text(
                            text=msg["text"]
                        )
                    ]
                )
            )

        # 3. Send request to Gemini
        start = time.perf_counter()

        chat = bot.ai_client.chats.create(
            model=MODEL_NAME,
            history=gemini_history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                thinking_config=types.ThinkingConfig(
                    thinking_level="low"
                ),
                max_output_tokens=256
            )
        )

        response = await chat.send_message(question)

        gemini_time = time.perf_counter() - start

        answer = response.text or "I couldn't generate a response."

        # 4. Save conversation
        db_history.append({
            "role": "user",
            "text": question
        })

        db_history.append({
            "role": "model",
            "text": answer
        })

        start = time.perf_counter()

        await bot.chats_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "history": db_history
                }
            },
            upsert=True
        )

        db_save_time = time.perf_counter() - start

        # 5. Print performance information
        total_time = (
            db_read_time +
            gemini_time +
            db_save_time
        )

        print(
            f"\n[ASK PERFORMANCE] "
            f"DB Read: {db_read_time:.2f}s | "
            f"Gemini: {gemini_time:.2f}s | "
            f"DB Save: {db_save_time:.2f}s | "
            f"Total: {total_time:.2f}s"
        )

        # 6. Send response to Discord
        if len(answer) > 2000:
            answer = answer[:1997] + "..."

        await interaction.followup.send(answer)

    except Exception as e:

        import traceback
        traceback.print_exc()

        await interaction.followup.send(
            f"Sorry, an error occurred: {e}"
        )


# =========================
# Reset Command
# =========================

@bot.tree.command(
    name="reset",
    description="Delete your conversation memory"
)
async def reset(
    interaction: discord.Interaction
):

    user_id = str(interaction.user.id)

    try:

        result = await bot.chats_collection.delete_one(
            {"_id": user_id}
        )

        if result.deleted_count > 0:

            await interaction.response.send_message(
                "Your conversation memory has been deleted!"
            )

        else:

            await interaction.response.send_message(
                "You don't have any saved conversation history."
            )

    except Exception as e:

        import traceback
        traceback.print_exc()

        await interaction.response.send_message(
            f"An error occurred: {e}"
        )


# =========================
# Start Bot
# =========================

if __name__ == "__main__":

    discord_token = os.getenv("DISCORD_TOKEN")

    if not discord_token:
        raise ValueError("DISCORD_TOKEN is missing!")

    bot.run(discord_token)

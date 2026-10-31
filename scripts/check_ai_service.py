import asyncio

from services.ai_service import AIService


async def main():
    ai = AIService()

    try:
        answer = await ai.generate_response(
            "يا فهيم، إحنا قاعدين زهقانين في الوكالة ومفيش حد بيتكلم. عندك حاجة نعملها؟"
        )
        print("\nFahim's response:\n")
        print(answer)

    finally:
        await ai.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

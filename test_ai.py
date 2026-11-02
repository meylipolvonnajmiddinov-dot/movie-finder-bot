import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from services.gemini_ai import analyze_text

async def main():
    result = await analyze_text("Bir odam tush ichida tush ko'radi, aylanuvchi totem")
    print(result)

asyncio.run(main())
import uvicorn
import asyncio
import logging

from userbot_gifter.app import app

import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")


async def start():
    try:
        config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", "5050")))
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        logger.error(f"Fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(start())
import asyncio
import logging
import signal

from pyrogram import Client
from pyrogram.errors import RPCError

from config.settings import get_settings
from database.db import Database
from handlers import commands, events
from modules.context import AppContext
from utils.security import RateLimiter


async def main():
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    log = logging.getLogger("demon-admin")
    db = Database(settings.mongo_uri, settings.mongo_db)
    await db.connect()

    app = Client(
        "demon_admin",
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        bot_token=settings.bot_token,
        workers=16,
        max_concurrent_transmissions=8,
    )
    ctx = AppContext(app=app, db=db, settings=settings, rate_limiter=RateLimiter(settings.command_rate_limit, settings.command_rate_window))
    commands.register(app, ctx)
    events.register(app, ctx)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, stop.set)
        except NotImplementedError: pass

    await app.start()
    me = await app.get_me()
    log.info("Started @%s", me.username)
    try:
        await stop.wait()
    finally:
        await app.stop()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

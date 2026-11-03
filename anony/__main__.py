# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import asyncio
import signal
import importlib

from anony import (anon, app, config, db, logger,
                   stop, tasks, thumb, userbot, yt)
from anony.plugins import all_modules


async def idle():
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    except NotImplementedError:
        def handler(sig, frame):
            loop.call_soon_threadsafe(stop_event.set)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    await stop_event.wait()

async def start_webapp():
    """The mini 'room' webapp — runs alongside the bot, not instead of
    it. Safe to skip: if it fails to start, the bot keeps working as
    before, just without the website."""
    if not config.WEBAPP_ENABLED:
        logger.info("Mini webapp disabled (WEBAPP_ENABLED=False).")
        return
    try:
        import uvicorn
        from anony.web import create_app

        server = uvicorn.Server(
            uvicorn.Config(
                create_app(),
                host=config.HOST,
                port=config.PORT,
                log_level="warning",
                loop="none",
            )
        )
        server.install_signal_handlers = lambda: None
        task = asyncio.ensure_future(server.serve())
        tasks.append(task)
        logger.info(f"Mini webapp running on :{config.PORT} ✅")
    except Exception as e:
        logger.warning(f"Mini webapp failed to start, bot continues without it: {e}")


async def main():
    await db.connect()
    await app.boot()
    await userbot.boot()
    await anon.boot()
    await thumb.start()
    await start_webapp()

    for module in all_modules:
        importlib.import_module(f"anony.plugins.{module}")
    logger.info(f"Loaded {len(all_modules)} modules.")

    if config.COOKIES_URL:
        await yt.save_cookies(config.COOKIES_URL)

    sudoers = await db.get_sudoers()
    app.sudoers.update(sudoers)
    app.bl_users.update(await db.get_blacklisted())
    logger.info(f"Loaded {len(app.sudoers)} sudo users.")

    await idle()
    await stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as ex:
        raise SystemExit(ex)

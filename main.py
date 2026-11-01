import asyncio
import logging
import signal
import sys
import traceback

import config
from BadMusic import Bad, LOGGER

# ── FastAPI WebApp ────────────────────────────────────────
async def run_webapp(bot: Bad, stop_event: asyncio.Event):
    import uvicorn
    from web.app import create_webapp, set_pyro_client

    set_pyro_client(bot)
    app = create_webapp()

    cfg = uvicorn.Config(
        app,
        host      = config.HOST,
        port      = config.PORT,   # Heroku sets $PORT dynamically — must bind to it
        log_level = "warning",
        loop      = "none",
    )
    server = uvicorn.Server(cfg)
    server.install_signal_handlers = lambda: None

    LOGGER.info(f"WebApp running on :{config.PORT} ✅")

    async def watch_stop():
        await stop_event.wait()
        server.should_exit = True

    asyncio.create_task(watch_stop())
    await server.serve()


# ── Voice Chat (assistant + PyTgCalls) ─────────────────────
async def start_vc(bot: Bad):
    """
    Builds + starts the assistant userbot and PyTgCalls, then wires
    RoomsManager → VC so every song also plays in the group's real
    Voice Chat (same file the web room is streaming). Safe to skip:
    if STRING_SESSION isn't set, the bot still runs web-room-only,
    exactly like before.

    Returns the assistant Client (or None) so main() can stop it
    cleanly on shutdown.

    NOTE: the assistant Client is created HERE, inside the running
    event loop (via create_assistant()) — not at module import time —
    otherwise Pyrogram binds it to the wrong asyncio loop and
    assistant.start() crashes with "attached to a different loop".
    """
    from BadMusic import create_assistant

    assistant, call_py = create_assistant()
    if assistant is None or call_py is None:
        LOGGER.warning("Voice Chat disabled (no STRING_SESSION) — web room only ✅")
        return None

    from core.player import rooms_manager
    from core.vc_manager import vc_manager
    from core.vc_sync import vc_sync_handler

    try:
        await assistant.start()
        me = await assistant.get_me()
        LOGGER.info(f"Assistant started: @{me.username or me.first_name} ✅")

        vc_manager.setup(call_py)
        await vc_manager.start()

        rooms_manager.set_vc_sync_callback(vc_sync_handler)
        LOGGER.info("Voice Chat streaming ENABLED — VC + Web room are now in sync ✅")
        return assistant
    except Exception as e:
        LOGGER.error(f"Voice Chat start failed, continuing web-room-only: {e}")
        traceback.print_exc()
        return None


# ── Main ──────────────────────────────────────────────────
async def main():
    try:
        from core.player import rooms_manager
        await rooms_manager.initialize()
        LOGGER.info("DB initialized ✅")
    except Exception as e:
        LOGGER.error(f"DB init failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    try:
        bot = Bad()
    except Exception as e:
        LOGGER.error(f"Bot creation failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    stop_event = asyncio.Event()

    def _shutdown(sig_name: str):
        if not stop_event.is_set():
            LOGGER.info(f"Received {sig_name} — shutting down...")
            stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _shutdown(s))
        except NotImplementedError:
            signal.signal(sig, lambda signum, frame, s=sig.name: _shutdown(s))

    async def post_start():
        await asyncio.sleep(2)
        try:
            from BadMusic.modules.settings import song_watchdog_all
            asyncio.create_task(song_watchdog_all(bot))
            LOGGER.info("Watchdog started ✅")
        except Exception as e:
            LOGGER.error(f"Watchdog failed to start: {e}")
            traceback.print_exc()

    asyncio.create_task(post_start())
    asyncio.create_task(run_webapp(bot, stop_event))

    try:
        await bot.start()
        LOGGER.info("Bad Music Bot is LIVE! ✅")
    except Exception as e:
        LOGGER.error(f"Bot start failed: {e}")
        traceback.print_exc()
        stop_event.set()
        sys.exit(1)

    vc_assistant = await start_vc(bot)

    await stop_event.wait()

    LOGGER.info("Stopping bot & web...")
    try:
        await bot.stop()
    except Exception as e:
        LOGGER.warning(f"Bot stop error: {e}")
    if vc_assistant is not None:
        try:
            await vc_assistant.stop()
        except Exception as e:
            LOGGER.warning(f"Assistant stop error: {e}")
    LOGGER.info("Goodbye! 👋")


# ── ENTRY ─────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Force stopped via KeyboardInterrupt.")
    except Exception as e:
        LOGGER.error(f"Fatal crash: {e}")
        traceback.print_exc()
    finally:
        LOGGER.info("Process exited.")
        sys.exit(0)
        

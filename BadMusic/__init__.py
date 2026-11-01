import logging
import time

from motor.motor_asyncio import AsyncIOMotorClient as MongoCli
from pyrogram import Client

import config

# ✅ ONLY TERMINAL LOGS (no file)
logging.basicConfig(
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    level=logging.INFO,
)

logging.getLogger("pyrogram").setLevel(logging.ERROR)
LOGGER = logging.getLogger(__name__)

boot = time.time()

# ── MongoDB ────────────────────────────────────────────────
if config.MONGO_URL:
    mongo = MongoCli(config.MONGO_URL)
    db = mongo[config.DB_NAME]
else:
    mongo = None
    db = None

OWNER = config.OWNER_ID

# ── Assistant (userbot) + PyTgCalls — real Voice Chat audio ──
# Mirrors ShizuMusic: a second account joins the group's VC and
# streams the same file that is playing in the web room, so a song
# plays in the Telegram Voice Chat AND in the mini web player at once.
#
# IMPORTANT: Pyrogram's Client binds itself to whatever asyncio loop
# is running at the moment it is constructed. Building it here, at
# *module import time*, happens BEFORE `asyncio.run(main())` creates
# the real loop — the Client then silently attaches to the wrong
# loop, and `assistant.start()` later crashes with:
#   "RuntimeError: Task ... got Future ... attached to a different loop"
# So we no longer construct it here. `create_assistant()` is a lazy
# factory — main.py calls it from *inside* the running loop instead
# (exactly like `bot = Bad()` already does for the main bot).
assistant = None
call_py   = None


def create_assistant():
    """Build the assistant Client + PyTgCalls instance. Must be called
    from inside the running asyncio loop (see main.py: start_vc)."""
    global assistant, call_py
    if not config.VC_ENABLED:
        LOGGER.warning("STRING_SESSION not set — Voice Chat streaming disabled, web room only.")
        return None, None
    try:
        from pytgcalls import PyTgCalls

        assistant = Client(
            "BadAssistant",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=config.STRING_SESSION,
            in_memory=True,
        )
        call_py = PyTgCalls(assistant)
        LOGGER.info("Assistant + PyTgCalls initialised ✅")
        return assistant, call_py
    except Exception as e:
        LOGGER.warning(f"VC init skipped (assistant/pytgcalls not ready): {e}")
        assistant = None
        call_py   = None
        return None, None


# ── Bot Client ─────────────────────────────────────────────
class Bad(Client):
    def __init__(self):
        super().__init__(
            name="BadMusic",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            plugins=dict(root="BadMusic.modules"),
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.id = me.id
        self.name = me.first_name
        self.username = me.username
        self.mention = me.mention

        LOGGER.info(f"✅ {self.name} (@{self.username}) started!")

        if config.LOGGER_ID:
            try:
                await self.send_message(
                    config.LOGGER_ID,
                    f"✅ **BadMusic Bot Started**\n"
                    f"• Name: {self.name}\n"
                    f"• Username: @{self.username}\n"
                    f"• ID: `{self.id}`",
                )
            except Exception as e:
                LOGGER.warning(f"Logger message failed: {e}")

    async def stop(self, *args):
        await super().stop()
        LOGGER.info("Bot stopped.")
        

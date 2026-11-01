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
assistant = None
call_py   = None

if config.VC_ENABLED:
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
    except Exception as e:
        LOGGER.warning(f"VC init skipped (assistant/pytgcalls not ready): {e}")
        assistant = None
        call_py   = None
else:
    LOGGER.warning("STRING_SESSION not set — Voice Chat streaming disabled, web room only.")


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
        

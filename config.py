# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll

"""
config.py — Central configuration (Pyrogram version)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Pyrogram / Telegram ────────────────────────────────────
API_ID       = int(os.getenv("API_ID",   "0"))
API_HASH     = os.getenv("API_HASH",     "YOUR_API_HASH")
BOT_TOKEN    = os.getenv("BOT_TOKEN",    "YOUR_BOT_TOKEN_HERE")
OWNER_ID     = int(os.getenv("OWNER_ID", "0"))
LOGGER_ID    = int(os.getenv("LOGGER_ID", "0"))
SUPPORT_CHAT = os.getenv("SUPPORT_CHAT", "https://t.me/PBXCHATS")

# ── Assistant / Voice-Chat (PyTgCalls) ──────────────────────
# A user-account session string is required so the bot can join and
# stream real audio inside a group's Telegram Voice Chat. Generate one
# with a "string session generator" (same account must be admin in the
# group, or allowed to join voice chats). Leave empty to disable VC
# streaming — the bot will still work as a web-only room player.
STRING_SESSION = os.getenv("STRING_SESSION", "")
VC_ENABLED     = bool(STRING_SESSION)

# ── WebApp ─────────────────────────────────────────────────
WEBAPP_URL   = os.getenv("WEBAPP_URL",   "https://your-domain.com")
MINIAPP_LINK = os.getenv("MINIAPP_LINK", "https://t.me/BadMusicBot/app")

# ── Database ───────────────────────────────────────────────
MONGO_URL    = os.getenv("MONGO_URL",    "")
DB_NAME      = os.getenv("DB_NAME",      "BadMusic")

# ── Server ─────────────────────────────────────────────────
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST",     "0.0.0.0")

# ── Downloads ──────────────────────────────────────────────
DOWNLOAD_DIR     = "static/downloads"
FALLBACK_API_URL = "https://shrutibots.site"
API_URL_PASTEBIN = "https://pastebin.com/raw/rLsBhAQa"

# ── Thumbnail (START_IMAGE) ────────────────────────────────
# Change this URL to update the bot's start/help thumbnail
START_IMAGE = os.getenv(
    "START_IMAGE",
    "https://files.catbox.moe/skgu94.jpg"   # ← apna image URL yahan paste karo
)

# ── Fallback Images ────────────────────────────────────────
# Shown when Telegram audio is played (no YouTube thumbnail)
TELEGRAM_AUDIO_URL = os.getenv(
    "TELEGRAM_AUDIO_URL",
    "https://telegra.ph/file/8234d704952738ebcda7f.jpg",
)
# Shown when YouTube thumbnail fetch fails
YOUTUBE_IMG_URL = os.getenv(
    "YOUTUBE_IMG_URL",
    "https://telegra.ph/file/76d29aa31c40a7f026d7e.jpg",
)

# ── Admin cache (per-group, populated by dispatcher) ──────
# {chat_id: [user_id, ...]}
adminlist: dict = {}

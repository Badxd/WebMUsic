from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from core.utils import make_progress_bar


# ── Start ─────────────────────────────────────────────────
def start_kb(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ɢʀᴏᴜᴩ",
            url=f"https://t.me/{bot_username}?startgroup=true",
        )],
        [
            InlineKeyboardButton("🛡️ sᴜᴩᴩᴏʀᴛ", url=config.SUPPORT_GROUP),
            InlineKeyboardButton("🛡️ ᴜᴘᴅᴀᴛᴇ", url=config.UPDATES_CHANNEL),
            
        ],
        [InlineKeyboardButton("📖 ʜᴇʟᴩ",    callback_data="help_menu"),],
    ])


# ── Help ──────────────────────────────────────────────────
def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ ᴀᴅᴍɪɴ",  callback_data="hb_admin"),
            InlineKeyboardButton("🔐 ᴀᴜᴛʜ",   callback_data="hb_auth"),
        ],
        [
            InlineKeyboardButton("🎵 ᴘʟᴀʏ",   callback_data="hb_play"),
            InlineKeyboardButton("📶 ᴘɪɴɢ",   callback_data="hb_ping"),
        ],
        [InlineKeyboardButton("⚙️ sᴇᴛᴛɪɴɢs", callback_data="hb_settings")],
        [InlineKeyboardButton("🛡️ sᴜᴩᴩᴏʀᴛ",  url=config.SUPPORT_GROUP)],
        [InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯",   callback_data="close")],
    ])


def help_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ sᴜᴩᴩᴏʀᴛ", url=config.SUPPORT_GROUP)],
        [InlineKeyboardButton("« ʙᴀᴄᴋ",      callback_data="help_menu")],
    ])


# ── Stream / Now Playing ──────────────────────────────────
def stream_kb(chat_id: int, played: str = "0:00",
              dur: str = "0:00", wl: str = "") -> InlineKeyboardMarkup:
    bar = make_progress_bar(played, dur)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{played} {bar} {dur}", callback_data="GetTimer")],
        [
            InlineKeyboardButton("▷",   callback_data=f"STREAM Resume|{chat_id}"),
            InlineKeyboardButton("II",  callback_data=f"STREAM Pause|{chat_id}"),
            InlineKeyboardButton("‣‣I", callback_data=f"STREAM Skip|{chat_id}"),
            InlineKeyboardButton("▢",   callback_data=f"STREAM Stop|{chat_id}"),
        ],
        [InlineKeyboardButton("🎧 ᴊᴏɪɴ ʀᴏᴏᴍ", url=wl or config.MINIAPP_LINK)],
        [
            InlineKeyboardButton("🛡️ sᴜᴩᴩᴏʀᴛ", url=config.SUPPORT_GROUP),
            InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯",  callback_data="close"),
        ],
    ])


# ── Queue ─────────────────────────────────────────────────
def queue_kb(wl: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 ᴊᴏɪɴ ʀᴏᴏᴍ ᴛᴏ ʟɪsᴛᴇɴ", url=wl or config.MINIAPP_LINK)],
        [
            InlineKeyboardButton("🛡️ sᴜᴩᴩᴏʀᴛ", url=config.SUPPORT_GROUP),
            InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯",  callback_data="close"),
        ],
    ])


# ── Session Ended ─────────────────────────────────────────
def ended_kb(wl: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 ᴊᴏɪɴ ʀᴏᴏᴍ", url=wl or config.MINIAPP_LINK)],
        [InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯", callback_data="close")],
    ])


# ── Queue list ────────────────────────────────────────────
def queuelist_kb(wl: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 ᴡᴇʙᴀᴩᴩ", url=wl or config.MINIAPP_LINK)],
        [InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯", callback_data="close")],
    ])


# ── Join Announce ─────────────────────────────────────────
def join_kb(wl: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 ᴊᴏɪɴ ʀᴏᴏᴍ", url=wl or config.MINIAPP_LINK)],
    ])


# ── Settings ──────────────────────────────────────────────
def settings_kb(chat_id: int, join_on: bool, queue_on: bool) -> InlineKeyboardMarkup:
    j = "✅" if join_on  else "❌"
    q = "✅" if queue_on else "❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{j} ᴊᴏɪɴ ᴀɴɴᴏᴜɴᴄᴇ",  callback_data=f"SET join|{chat_id}")],
        [InlineKeyboardButton(f"{q} ǫᴜᴇᴜᴇ ᴀɴɴᴏᴜɴᴄᴇ", callback_data=f"SET queue|{chat_id}")],
        [InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯", callback_data="close")],
    ])


# ── Active rooms ──────────────────────────────────────────
def active_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✯ ᴄʟᴏsᴇ ✯", callback_data="close")],
    ])


# ── Anonymous admin warning ───────────────────────────────
def anon_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ʜᴏᴡ ᴛᴏ ꜰɪx?", callback_data="AnonymousAdmin")],
    ])

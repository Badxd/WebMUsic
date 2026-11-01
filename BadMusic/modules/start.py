# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll

"""
BadMusic/modules/start.py
/start — with image + logger
/help  — with image + buttons
"""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

import config
from BadMusic.modules.helpers import delete_after, log_activity
from BadMusic.modules.buttons import start_kb, help_kb, help_back_kb
from strings import get_string

logger = logging.getLogger("Start")

# ── Thumbnail ─────────────────────────────────────────────
# Replace START_IMAGE in config.py to change the thumbnail
# config.START_IMAGE = "https://files.catbox.moe/skgu94.jpg"  (default)

# ── /start ─────────────────────────────────────────────────
@Client.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    _ = get_string("en")
    user = message.from_user
    chat = message.chat

    try:
        await message.delete()
    except Exception:
        pass

    # ── Group: just send welcome ───────────────────────────
    if chat.type.value in ("group", "supergroup"):
        msg = await client.send_message(chat.id, _["start_group"])
        asyncio.create_task(delete_after(client, chat.id, msg.id, 10))
        return

    # ── Private: send image + buttons ─────────────────────
    asyncio.create_task(log_activity(client,
        f"🚀 **Bot Started**\n\n"
        f"👤 **User:** [{user.first_name}](tg://user?id={user.id})\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"📛 **Username:** @{user.username or 'N/A'}"
    ))

    me      = await client.get_me()
    caption = _["start_caption"].format(
        first_name = user.first_name,
        user_id    = user.id,
    )
    kb = start_kb(me.username)

    try:
        await client.send_photo(
            chat.id,
            photo        = config.START_IMAGE,
            caption      = caption,
            reply_markup = kb,
        )
    except Exception:
        await client.send_message(chat.id, caption, reply_markup=kb)


# ── /help ──────────────────────────────────────────────────
@Client.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await _send_help(client, message.chat.id)


async def _send_help(client: Client, chat_id: int, msg_to_edit=None):
    _ = get_string("en")
    text = _["help_text"].format(support=config.SUPPORT_CHAT)
    kb   = help_kb()

    if msg_to_edit:
        try:
            await msg_to_edit.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    try:
        await client.send_photo(
            chat_id,
            photo        = config.START_IMAGE,
            caption      = text,
            reply_markup = kb,
        )
    except Exception:
        await client.send_message(chat_id, text, reply_markup=kb)


# ── Callback: help sections ────────────────────────────────
@Client.on_callback_query(filters.regex("^hb_"))
async def help_callback(client: Client, cb: CallbackQuery):
    _ = get_string("en")
    data = cb.data

    if data == "hb_settings":
        await cb.answer("ᴜsᴇ /setting ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴩ", show_alert=True)
        return

    key_map = {
        "hb_admin": "help_admin",
        "hb_auth":  "help_auth",
        "hb_play":  "help_play",
        "hb_ping":  "help_ping",
    }
    text = _.get(key_map.get(data, ""), "")
    if not text:
        await cb.answer()
        return

    await cb.message.edit_text(text, reply_markup=help_back_kb())
    await cb.answer()


@Client.on_callback_query(filters.regex("^help_menu$"))
async def help_menu_cb(client: Client, cb: CallbackQuery):
    await _send_help(client, cb.message.chat.id, msg_to_edit=cb.message)
    await cb.answer()


@Client.on_callback_query(filters.regex("^close$"))
async def close_cb(client: Client, cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()

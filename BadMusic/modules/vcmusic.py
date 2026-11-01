# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll

"""
BadMusic/modules/vcmusic.py
/vcmusic — turn real Telegram Voice-Chat streaming ON/OFF, your own
choice, whenever you want:

  /vcmusic           → show current status for this group
  /vcmusic on        → enable VC streaming for THIS group  (group admin)
  /vcmusic off       → disable VC streaming for THIS group (group admin)
  /vcmusic global on → enable VC bot-wide                   (owner only)
  /vcmusic global off→ disable VC bot-wide, no .env restart needed (owner only)

Groups that switch it off stay web-room-only — zero assistant/ffmpeg
load for them — while every other group keeps real VC audio.
"""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import Message

import config
from BadMusic.modules.helpers import delete_after, is_admin
from core.player import rooms_manager
from core.vc_manager import vc_manager
from database import db

logger = logging.getLogger("VCMusicCmd")


@Client.on_message(filters.command(["vcmusic", "vcmode"]) & filters.group)
async def vcmusic_cmd(client: Client, message: Message):
    try:
        await message.delete()
    except Exception:
        pass

    chat_id = message.chat.id
    args = message.command[1:] if len(message.command) > 1 else []

    # ── /vcmusic global on|off — owner only, bot-wide switch ──
    if args and args[0].lower() == "global":
        if message.from_user.id != config.OWNER_ID:
            msg = await client.send_message(chat_id, "🚫 Sirf bot owner hi global VC switch use kar sakda hai.")
            asyncio.create_task(delete_after(client, chat_id, msg.id, 6))
            return
        if len(args) < 2 or args[1].lower() not in ("on", "off"):
            msg = await client.send_message(chat_id, "Use: `/vcmusic global on` ya `/vcmusic global off`")
            asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
            return

        enabled = args[1].lower() == "on"
        await db.set_vc_global(enabled)
        state = "✅ ON — har group vich real VC streaming chalu" if enabled else "🔴 OFF — sab groups web-room-only (VC band)"
        msg = await client.send_message(chat_id, f"🌐 **Global Voice Chat:** {state}")
        asyncio.create_task(delete_after(client, chat_id, msg.id, 10))
        return

    # ── /vcmusic (no args) — status ──
    if not args:
        global_state = "ON ✅" if db._vc_global_enabled else "OFF 🔴"
        group_state  = "ON ✅" if db.is_vc_enabled(chat_id) else "OFF 🔴"
        avail = "ready" if vc_manager.is_available() else "not configured (no STRING_SESSION)"
        text = (
            "🎚 **Voice Chat Status**\n\n"
            f"• Is group: **{group_state}**\n"
            f"• Global (sab groups): **{global_state}**\n"
            f"• Assistant: `{avail}`\n\n"
            "On/Off karan laayi: `/vcmusic on` ya `/vcmusic off`"
        )
        msg = await client.send_message(chat_id, text)
        asyncio.create_task(delete_after(client, chat_id, msg.id, 15))
        return

    # ── /vcmusic on|off — this group, group-admin only ──
    if args[0].lower() not in ("on", "off"):
        msg = await client.send_message(chat_id, "Use: `/vcmusic on` ya `/vcmusic off`")
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    if not await is_admin(client, chat_id, message.from_user.id):
        from strings import get_string
        _ = get_string("en")
        msg = await client.send_message(chat_id, _["admin_only"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 6))
        return

    enabled = args[0].lower() == "on"
    await db.set_vc_for_chat(chat_id, enabled)

    if enabled:
        text = "📞 **Voice Chat streaming ON** is group vich — ab gaana web room + real VC dono vich chalu hoyega."
    else:
        text = "🔇 **Voice Chat streaming OFF** is group vich — sirf web room chalu rahu, koi extra load nahi."
        # leave VC right away so load drops immediately, no need to wait
        # for the next song/skip event
        try:
            await vc_manager.leave(chat_id)
        except Exception as e:
            logger.debug(f"leave on disable [{chat_id}]: {e}")

    msg = await client.send_message(chat_id, text)
    asyncio.create_task(delete_after(client, chat_id, msg.id, 10))

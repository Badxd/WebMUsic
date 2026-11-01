"""
BadMusic/modules/events.py
Logs: bot added/removed from group, user kicked/banned
Pyrogram ChatMemberUpdated handler
"""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatMemberUpdated

import config
from BadMusic.modules.helpers import log_activity

logger = logging.getLogger("Events")


@Client.on_chat_member_updated()
async def member_update(client: Client, update: ChatMemberUpdated):
    try:
        chat    = update.chat
        user    = update.new_chat_member.user if update.new_chat_member else None
        done_by = update.from_user

        if not user:
            return

        old_status = update.old_chat_member.status if update.old_chat_member else None
        new_status = update.new_chat_member.status  if update.new_chat_member else None

        # ── Bot added to group ─────────────────────────
        if user.is_self and new_status == ChatMemberStatus.MEMBER:
            asyncio.create_task(log_activity(client,
                f"➕ **Bot Added To Group**\n\n"
                f"👤 **By:** [{done_by.first_name}](tg://user?id={done_by.id})\n"
                f"🆔 **User ID:** `{done_by.id}`\n"
                f"💬 **Group:** {chat.title or 'Unknown'}\n"
                f"🆔 **Group ID:** `{chat.id}`"
            ))

        # ── Bot removed from group ─────────────────────
        elif user.is_self and new_status in (
            ChatMemberStatus.BANNED, ChatMemberStatus.LEFT
        ):
            asyncio.create_task(log_activity(client,
                f"➖ **Bot Removed From Group**\n\n"
                f"👤 **By:** [{done_by.first_name}](tg://user?id={done_by.id})\n"
                f"🆔 **User ID:** `{done_by.id}`\n"
                f"💬 **Group:** {chat.title or 'Unknown'}\n"
                f"🆔 **Group ID:** `{chat.id}`"
            ))

        # ── User kicked / banned (not self) ───────────
        elif (
            not user.is_self
            and old_status in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.RESTRICTED,
            )
            and new_status in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT)
            and done_by
            and done_by.id != user.id
        ):
            asyncio.create_task(log_activity(client,
                f"🚫 **User Kicked / Banned**\n\n"
                f"👤 **User:** [{user.first_name}](tg://user?id={user.id})\n"
                f"🆔 **User ID:** `{user.id}`\n"
                f"🔨 **By:** [{done_by.first_name}](tg://user?id={done_by.id})\n"
                f"💬 **Group:** {chat.title}\n"
                f"🆔 **Group ID:** `{chat.id}`\n"
                f"📌 **Status:** {'Banned 🔴' if new_status == ChatMemberStatus.BANNED else 'Kicked ⚠️'}"
            ))

    except Exception as e:
        logger.error(f"member_update: {e}")

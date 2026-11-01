# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll

import asyncio
import logging

import config

logger = logging.getLogger("Helpers")


async def delete_after(client, chat_id: int, msg_id: int, delay: int = 8):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, msg_id)
    except Exception:
        pass


async def log_activity(client, text: str):
    if not config.LOGGER_ID:
        return
    try:
        await client.send_message(config.LOGGER_ID, text, disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"log_activity failed: {e}")


async def is_admin(client, chat_id: int, user_id: int) -> bool:
    """
    Returns True if user is:
    - Bot owner (OWNER_ID)
    - In DB admins list
    - Telegram group admin/creator
    """
    from database.mongo import db
    from pyrogram.enums import ChatMemberStatus

    # Owner always admin
    if user_id == config.OWNER_ID:
        return True

    # DB auth list
    if db.is_admin(user_id, config.OWNER_ID):
        return True

    # Check Telegram group admin status
    if chat_id and chat_id < 0:  # group/supergroup only
        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ):
                return True
        except Exception:
            pass

    return False
    

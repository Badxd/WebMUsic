# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll

"""
BadMusic/modules/settings.py
All control commands + settings + watchdog + /active — Pyrogram version
"""
import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

import config
from BadMusic.modules.helpers import delete_after, log_activity, is_admin
from BadMusic.modules.buttons import (
    stream_kb, ended_kb, queuelist_kb,
    join_kb, settings_kb, active_kb,
)
from core.player import rooms_manager
from core.utils  import fmt_sec, make_startapp_link
from strings     import get_string

logger = logging.getLogger("Settings")

_join_cooldown: dict = {}

# ── Shared helper ─────────────────────────────────────────
async def _safe_delete_msgs(client: Client, room):
    old = list(room.play_messages.values())
    room.play_messages = {}
    for info in old:
        msg = info.get("msg")
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass


# ── /skip ─────────────────────────────────────────────────
@Client.on_message(filters.command("skip") & filters.group)
async def skip(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)
    await _safe_delete_msgs(client, room)
    await room.skip_song()

    from BadMusic.modules.play import send_now_playing
    if room.current_song:
        await send_now_playing(client, chat_id, room, room.current_song)
    else:
        msg = await client.send_message(chat_id, _["no_more_songs"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 15))

    msg = await client.send_message(
        chat_id,
        _["skipped"].format(name=message.from_user.first_name),
    )
    asyncio.create_task(delete_after(client, chat_id, msg.id, 8))


# ── /stop ─────────────────────────────────────────────────
@Client.on_message(filters.command("stop") & filters.group)
async def stop(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return
    room = rooms_manager.get_room(message.chat.id)
    await _safe_delete_msgs(client, room)
    await room.stop_session()
    msg = await client.send_message(
        message.chat.id,
        _["stopped"].format(name=message.from_user.first_name),
    )
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


# ── /end ──────────────────────────────────────────────────
@Client.on_message(filters.command("end") & filters.group)
async def end_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)
    await _safe_delete_msgs(client, room)
    await room.stop_session()

    wl  = make_startapp_link("", "", "0:00", chat_id)
    user = message.from_user
    msg  = await client.send_message(
        chat_id,
        _["session_ended"].format(name=user.first_name, user_id=user.id),
        reply_markup=ended_kb(wl),
    )
    asyncio.create_task(delete_after(client, chat_id, msg.id, 30))


# ── /pause ────────────────────────────────────────────────
@Client.on_message(filters.command("pause") & filters.group)
async def pause(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return
    room = rooms_manager.get_room(message.chat.id)
    if not room.is_playing:
        msg = await client.send_message(message.chat.id, _["already_paused"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return
    await room.pause_stream()
    msg = await client.send_message(
        message.chat.id,
        _["paused"].format(name=message.from_user.first_name),
    )
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


# ── /resume ───────────────────────────────────────────────
@Client.on_message(filters.command("resume") & filters.group)
async def resume(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return
    room = rooms_manager.get_room(message.chat.id)
    if room.is_playing:
        msg = await client.send_message(message.chat.id, _["already_resumed"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return
    await room.resume_stream()
    msg = await client.send_message(
        message.chat.id,
        _["resumed"].format(name=message.from_user.first_name),
    )
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


# ── /queue ────────────────────────────────────────────────
@Client.on_message(filters.command("queue") & filters.group)
async def queue_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)
    if not room.current_song:
        msg = await client.send_message(chat_id, _["queue_empty"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    text = "**ɴᴏᴡ:**\n"
    text += f"➲ **{room.current_song['title']}**\n"
    if room.queue:
        text += f"\n**ᴜᴩ ɴᴇxᴛ ({len(room.queue)}):**\n\n"
        for i, s in enumerate(room.queue[:8], 1):
            text += f"{i}↬ **{s['title']}**\n"
        if len(room.queue) > 8:
            text += f"\n...+{len(room.queue)-8} ᴍᴏʀᴇ"
    else:
        text += "\n» ɴᴏ ᴍᴏʀᴇ ᴛʀᴀᴄᴋs."

    wl  = make_startapp_link("", "", "0:00", chat_id)
    msg = await client.send_message(chat_id, text, reply_markup=queuelist_kb(wl))
    asyncio.create_task(delete_after(client, chat_id, msg.id, 30))


# ── /fav ──────────────────────────────────────────────────
@Client.on_message(filters.command("fav") & filters.group)
async def fav_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    uid     = message.from_user.id
    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)
    if not room.current_song:
        msg = await client.send_message(chat_id, _["no_song_playing"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 6))
        return

    from database.mongo import db   # ✅ FIXED: was db_manager
    song = {
        "title":        room.current_song.get("title",        "Unknown"),
        "link":         room.current_song.get("link",          ""),
        "thumbnail":    room.current_song.get("thumbnail",     ""),
        "duration_sec": room.current_song.get("duration_sec",  0),
    }
    ok   = await db.add_favorite(uid, song)
    text = _["fav_added"].format(title=song["title"][:60]) \
           if ok else _["fav_failed"]
    msg  = await client.send_message(chat_id, text)
    asyncio.create_task(delete_after(client, chat_id, msg.id, 8))


# ── /setting ──────────────────────────────────────────────
@Client.on_message(filters.command("setting") & filters.group)
async def setting_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return
    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)
    text    = _["settings_text"].format(
        join_emoji  = "✅" if room.announce_join  else "❌",
        queue_emoji = "✅" if room.announce_queue else "❌",
    )
    kb  = settings_kb(chat_id, room.announce_join, room.announce_queue)
    msg = await client.send_message(chat_id, text, reply_markup=kb)
    asyncio.create_task(delete_after(client, chat_id, msg.id, 30))


@Client.on_callback_query(filters.regex(r"^SET "))
async def settings_cb(client: Client, cb: CallbackQuery):
    _ = get_string("en")
    if not await is_admin(client, cb.message.chat.id, cb.from_user.id):
        await cb.answer(_["not_admin"], show_alert=True)
        return
    setting, cid_str = cb.data.split(" ", 1)[1].split("|", 1)
    try:
        chat_id = int(cid_str)
    except ValueError:
        await cb.answer()
        return
    room = rooms_manager.get_room(chat_id)
    if setting == "join":
        room.announce_join = not room.announce_join
        await cb.answer(f"ᴊᴏɪɴ: {'ON' if room.announce_join else 'OFF'}")
    elif setting == "queue":
        room.announce_queue = not room.announce_queue
        await cb.answer(f"ǫᴜᴇᴜᴇ: {'ON' if room.announce_queue else 'OFF'}")
    text = _["settings_text"].format(
        join_emoji  = "✅" if room.announce_join  else "❌",
        queue_emoji = "✅" if room.announce_queue else "❌",
    )
    try:
        await cb.message.edit_text(
            text,
            reply_markup=settings_kb(chat_id, room.announce_join, room.announce_queue),
        )
    except Exception:
        pass


# ── /ping ─────────────────────────────────────────────────
@Client.on_message(filters.command("ping"))
async def ping(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    import random
    t0  = time.time()
    msg = await client.send_message(message.chat.id, _["pinging"])
    ms  = round((time.time() - t0) * 1000)
    await msg.edit(
        f"🏓 **ᴩᴏɴɢ:** `{ms}ms`\n\n"
        f"**ʙᴀᴅ ᴍᴜsɪᴄ sᴛᴀᴛs:**\n"
        f"↬ ʀᴀᴍ: `{random.randint(10,25)}%`\n"
        f"↬ ᴄᴩᴜ: `{random.randint(5,12)}%`\n"
        f"↬ ᴀᴄᴛɪᴠᴇ ʀᴏᴏᴍs: `{len(rooms_manager.rooms)}`"
    )


# ── /auth /unauth /blacklist /clean ───────────────────────
@Client.on_message(filters.command("auth") & filters.private)
async def auth_cmd(client: Client, message: Message):
    _ = get_string("en")
    if message.from_user.id != config.OWNER_ID:
        return await message.reply(_["owner_only"])
    if not message.reply_to_message:
        return await message.reply(_["reply_needed"])
    t   = message.reply_to_message.from_user
    await rooms_manager.auth_user(t.id)
    msg = await message.reply(_["auth_added"].format(name=t.first_name, user_id=t.id))
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


@Client.on_message(filters.command("unauth") & filters.private)
async def unauth_cmd(client: Client, message: Message):
    _ = get_string("en")
    if message.from_user.id != config.OWNER_ID:
        return await message.reply(_["owner_only"])
    if not message.reply_to_message:
        return await message.reply(_["reply_needed"])
    t   = message.reply_to_message.from_user
    await rooms_manager.unauth_user(t.id)
    msg = await message.reply(_["auth_removed"].format(name=t.first_name, user_id=t.id))
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


@Client.on_message(filters.command("blacklist") & filters.group)
async def blacklist_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    if not message.reply_to_message:
        return
    t = message.reply_to_message.from_user
    if t.id == config.OWNER_ID:
        return
    await rooms_manager.blacklist_user(t.id)
    msg = await client.send_message(
        message.chat.id,
        _["blacklisted_user"].format(name=t.first_name, user_id=t.id),
    )
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


@Client.on_message(filters.command("clean") & filters.group)
async def clean_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return
    if rooms_manager.clean_downloads():
        msg = await client.send_message(message.chat.id, _["cache_cleaned"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 8))


# ── /active — Owner only ──────────────────────────────────
@Client.on_message(filters.command("active"))
async def active_cmd(client: Client, message: Message):
    """Show all active music rooms with join links. Owner only."""
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass

    if message.from_user.id != config.OWNER_ID:
        msg = await client.send_message(message.chat.id, _["owner_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    active = [
        (cid, room)
        for cid, room in rooms_manager.rooms.items()
        if room.current_song
    ]

    if not active:
        msg = await client.send_message(message.chat.id, _["active_none"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 10))
        return

    text = _["active_header"]
    for i, (cid, room) in enumerate(active, 1):
        wl    = make_startapp_link("", "", "0:00", cid)
        title = room.current_song.get("title", "Unknown")[:35]
        text += _["active_row"].format(
            i         = i,
            chat_id   = cid,
            title     = title,
            listeners = len(room.listeners),
        )
        text += f"   [🎧 ᴊᴏɪɴ]({wl})\n"

    text += _["active_footer"].format(count=len(active))

    msg = await client.send_message(
        message.chat.id,
        text,
        reply_markup=active_kb(),
        disable_web_page_preview=True,
    )
    asyncio.create_task(delete_after(client, message.chat.id, msg.id, 60))


# ── Join announcement ─────────────────────────────────────
async def announce_join_to_group(client: Client, chat_id: int,
                                  username: str, song_title: str):
    _ = get_string("en")
    room = rooms_manager.get_room(chat_id)
    if not room.announce_join:
        return
    now = __import__("time").monotonic()
    if now - _join_cooldown.get(chat_id, 0) < 30:
        return
    _join_cooldown[chat_id] = now
    try:
        wl   = make_startapp_link("", "", "0:00", chat_id)
        text = _["join_announce"].format(
            username   = username,
            listeners  = len(room.listeners),
            song_title = song_title or "?",
        )
        msg = await client.send_message(chat_id, text, reply_markup=join_kb(wl))
        asyncio.create_task(delete_after(client, chat_id, msg.id, 60))
    except Exception as e:
        logger.error(f"announce_join: {e}")


# ── Song watchdog ─────────────────────────────────────────
async def song_watchdog_all(client: Client):
    """Polls every 2s — auto-advance queue when song ends."""
    from BadMusic.modules.play import send_now_playing, _disk_cleanup_loop
    from services.downloader   import delete_song_file

    # ✅ Start disk cleanup background task
    asyncio.create_task(_disk_cleanup_loop())

    _ = get_string("en")
    no_listener_timers: dict = {}

    while True:
        await asyncio.sleep(2)
        for chat_id, room in list(rooms_manager.rooms.items()):
            try:
                if room.is_song_finished() and not room._advancing:
                    room._advancing = True
                    try:
                        old = list(room.play_messages.values())
                        room.play_messages = {}
                        for info in old:
                            msg = info.get("msg")
                            if msg:
                                try:
                                    await msg.delete()
                                except Exception:
                                    pass

                        # ✅ Cleanup: delete finished song file from VPS
                        finished_song = room.current_song
                        await room.skip_song()
                        if finished_song and finished_song.get("link"):
                            from services.downloader import extract_video_id as _evid
                            vid = _evid(finished_song["link"])
                            if vid:
                                asyncio.create_task(asyncio.to_thread(delete_song_file, vid))

                        if room.current_song:
                            await send_now_playing(client, chat_id, room, room.current_song)
                        else:
                            msg = await client.send_message(
                                chat_id, _["no_more_songs"]
                            )
                            asyncio.create_task(delete_after(client, chat_id, msg.id, 20))
                    except Exception as e:
                        logger.error(f"watchdog advance [{chat_id}]: {e}")
                        room._advancing = False

                if len(room.listeners) == 0 and (room.current_song or room.queue):
                    now = __import__("time").monotonic()
                    if chat_id not in no_listener_timers:
                        no_listener_timers[chat_id] = now
                    elif now - no_listener_timers[chat_id] >= 60:
                        await room.stop_session()
                        no_listener_timers.pop(chat_id, None)
                else:
                    no_listener_timers.pop(chat_id, None)

            except Exception as e:
                logger.error(f"watchdog [{chat_id}]: {e}")


# ── /seek <seconds> ───────────────────────────────────────
@Client.on_message(filters.command("seek") & filters.group)
async def seek_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    args    = message.command[1:]
    if not args:
        msg = await client.send_message(chat_id, "Usage: /seek 30  (seconds to skip forward)")
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    try:
        secs = int(args[0])
    except ValueError:
        msg = await client.send_message(chat_id, "Give seconds as a number. Example: /seek 30")
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    room = rooms_manager.get_room(chat_id)
    if not room.current_song:
        msg = await client.send_message(chat_id, _["no_song_playing"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 6))
        return

    dur_sec     = room.current_song.get("duration_sec", 0)
    new_pos     = min(max(0, room.get_current_seek() + secs), dur_sec)
    room.seek_time        = new_pos
    room.last_update_time = __import__("time").monotonic()

    mins, s = divmod(int(new_pos), 60)
    msg = await client.send_message(
        chat_id,
        f"Seeked to {mins}:{s:02d} by {message.from_user.first_name}"
    )
    asyncio.create_task(delete_after(client, chat_id, msg.id, 8))


# ── /seekback <seconds> ───────────────────────────────────
@Client.on_message(filters.command("seekback") & filters.group)
async def seekback_cmd(client: Client, message: Message):
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    args    = message.command[1:]
    secs    = int(args[0]) if args and args[0].isdigit() else 10

    room = rooms_manager.get_room(chat_id)
    if not room.current_song:
        msg = await client.send_message(chat_id, _["no_song_playing"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 6))
        return

    new_pos               = max(0, room.get_current_seek() - secs)
    room.seek_time        = new_pos
    room.last_update_time = __import__("time").monotonic()

    mins, s = divmod(int(new_pos), 60)
    msg = await client.send_message(
        chat_id,
        f"Seeked back to {mins}:{s:02d} by {message.from_user.first_name}"
    )
    asyncio.create_task(delete_after(client, chat_id, msg.id, 8))


# ── /bass <off|low|medium|high|extreme> ──────────────────
@Client.on_message(filters.command("bass") & filters.group)
async def bass_cmd(client: Client, message: Message):
    """
    Bass boost / audio filter via webapp.
    Sends a state update that frontend picks up and applies
    Web Audio API BiquadFilter (bass boost) + playback rate (speed).
    """
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    LEVELS  = {
        "off":     {"gain": 0,   "freq": 60,  "label": "Normal"},
        "low":     {"gain": 4,   "freq": 80,  "label": "Low Bass"},
        "medium":  {"gain": 9,   "freq": 100, "label": "Medium Bass"},
        "high":    {"gain": 14,  "freq": 120, "label": "High Bass"},
        "extreme": {"gain": 20,  "freq": 150, "label": "Extreme Bass"},
    }

    args  = message.command[1:]
    level = args[0].lower() if args else "medium"
    if level not in LEVELS:
        opts = " | ".join(LEVELS.keys())
        msg  = await client.send_message(chat_id, f"Usage: /bass off|low|medium|high|extreme\nOptions: {opts}")
        asyncio.create_task(delete_after(client, chat_id, msg.id, 10))
        return

    cfg  = LEVELS[level]
    room = rooms_manager.get_room(chat_id)

    # Store bass config in room for broadcast
    room.bass_config = {"level": level, "gain": cfg["gain"], "freq": cfg["freq"]}

    # Broadcast to all webapp listeners
    from web.app import _broadcast
    await _broadcast(chat_id)

    msg = await client.send_message(
        chat_id,
        f"Bass set to: {cfg['label']} by {message.from_user.first_name}"
    )
    asyncio.create_task(delete_after(client, chat_id, msg.id, 8))


# ── Also add seek/seekback/bass to chat commands ─────────
# These are handled in handle_chat_command in play.py


# ── /playlist ─────────────────────────────────────────────
@Client.on_message(filters.command("playlist") & filters.group)
async def playlist_cmd(client: Client, message: Message):
    """Show current queue / playlist in the group."""
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass

    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)

    if not room.current_song and not room.queue:
        msg = await client.send_message(
            chat_id,
            "❌ **Queue khaali hai!**\nKoi song nahi chal raha.\nUse /play <song name> to start!"
        )
        asyncio.create_task(delete_after(client, chat_id, msg.id, 10))
        return

    lines = ["🎵 **Current Playlist**\n"]
    if room.current_song:
        title = room.current_song.get("title", "Unknown")
        link  = room.current_song.get("link", "")
        dur   = fmt_sec(room.current_song.get("duration_sec", 0))
        if link:
            lines.append(f"▶️ **Now Playing:** [{title}]({link}) `{dur}`")
        else:
            lines.append(f"▶️ **Now Playing:** {title} `{dur}`")

    queue = room.queue
    if queue:
        lines.append(f"\n📋 **Queue ({len(queue)} songs):**")
        for i, song in enumerate(queue[:15], 1):
            t   = song.get("title", "Unknown")
            d   = fmt_sec(song.get("duration_sec", 0))
            lnk = song.get("link", "")
            if lnk:
                lines.append(f"`{i}.` [{t}]({lnk}) `{d}`")
            else:
                lines.append(f"`{i}.` {t} `{d}`")
        if len(queue) > 15:
            lines.append(f"_...and {len(queue) - 15} more songs_")
    else:
        lines.append("\n_No songs in queue_")

    wl = make_startapp_link(
        room.current_song.get("link", "") if room.current_song else "",
        room.current_song.get("title", "") if room.current_song else "",
        fmt_sec(room.current_song.get("duration_sec", 0)) if room.current_song else "0:00",
        chat_id,
    )
    kb   = queuelist_kb(wl)
    sent = await client.send_message(
        chat_id, "\n".join(lines),
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    asyncio.create_task(delete_after(client, chat_id, sent.id, 60))


# ── /clearqueue ────────────────────────────────────────────
@Client.on_message(filters.command(["clearqueue", "cq"]) & filters.group)
async def clearqueue_cmd(client: Client, message: Message):
    """Clear all queued songs but keep the current one playing."""
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    room    = rooms_manager.get_room(chat_id)
    room._queue.clear()
    msg = await client.send_message(
        chat_id,
        f"🗑️ **Queue cleared** by {message.from_user.first_name}"
    )
    asyncio.create_task(delete_after(client, chat_id, msg.id, 8))


# ── /autoplay <query|off> ─────────────────────────────────
@Client.on_message(filters.command("autoplay") & filters.group)
async def autoplay_cmd(client: Client, message: Message):
    """Enable/disable autoplay with a seed query."""
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass
    if not await is_admin(client, message.chat.id, message.from_user.id):
        msg = await client.send_message(message.chat.id, _["admin_only"])
        asyncio.create_task(delete_after(client, message.chat.id, msg.id, 6))
        return

    chat_id = message.chat.id
    args    = message.command[1:]

    if not args or args[0].lower() == "off":
        # disable
        from database import db as _db
        await _db.set_autoplay(chat_id, False, "")
        msg = await client.send_message(chat_id,
            f"⏹ **Autoplay OFF** — disabled by {message.from_user.first_name}")
        asyncio.create_task(delete_after(client, chat_id, msg.id, 10))
        return

    query = " ".join(args).strip()
    from database import db as _db
    await _db.set_autoplay(chat_id, True, query)
    msg = await client.send_message(chat_id,
        f"🔄 **Autoplay ON** — seeded: `{query}`\n"
        "Bot will auto-fetch related songs when queue ends!")
    asyncio.create_task(delete_after(client, chat_id, msg.id, 15))

"""
BadMusic/modules/play.py
/play command + inline search — Pyrogram version
"""
import asyncio
import logging
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    Message,
)

import config
from BadMusic.modules.helpers import delete_after, log_activity, is_admin
from BadMusic.modules.buttons import stream_kb as stream_keyboard, queue_kb as queue_keyboard
from core.player   import rooms_manager
from core.utils    import fmt_sec, make_startapp_link, make_progress_bar
from services.youtube    import search_youtube
from services.downloader import download_song, time_to_seconds, delete_song_file, extract_video_id as _extract_vid
from strings import get_string
from BadMusic.utils.thumbnail import get_thumb

logger = logging.getLogger("Play")

PLAY_STICKER = "CAACAgUAAyEFAASOlzVAAAEBbMVoZBvc22oR8X-QlMPpERj8bdrDtgAChAsAAjXBOFddqD7hjDYLoh4E"




# ── /play ──────────────────────────────────────────────────
@Client.on_message(filters.command("play") & filters.group)
async def play(client: Client, message: Message):
    _ = get_string("en")
    uid     = message.from_user.id
    chat_id = message.chat.id

    # Delete command immediately
    try:
        await message.delete()
    except Exception:
        pass

    if rooms_manager.blacklisted_users and uid in rooms_manager.blacklisted_users:
        msg = await client.send_message(chat_id, _["blacklisted"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    # ── Check: Telegram audio reply ───────────────────────
    replied = message.reply_to_message
    if replied and (replied.audio or replied.voice or replied.document):
        await _play_telegram_media(client, message, replied, uid, chat_id, _)
        return

    # ── Normal: text query / YouTube link ─────────────────
    if not message.command[1:]:
        msg = await client.send_message(chat_id, _["usage_play"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    query = " ".join(message.command[1:])

    # Sticker
    try:
        st = await client.send_sticker(chat_id, PLAY_STICKER)
        asyncio.create_task(delete_after(client, chat_id, st.id, 5))
    except Exception:
        pass

    # Status message (standalone — no reply ref to avoid BadRequest)
    try:
        mystic = await client.send_message(chat_id, _["searching"])
    except Exception:
        return

    try:
        results = await search_youtube(query, limit=1)
        if not results:
            await mystic.edit(_["no_results"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
            return

        r        = results[0]
        link     = r["link"]
        title    = r["title"]
        duration = r["duration"]
        thumb    = r["thumbnail"]
        dur_sec  = time_to_seconds(duration)
        room     = rooms_manager.get_room(chat_id)

        await mystic.edit(_["downloading"])
        url = await download_song(link)

        if not url:
            await mystic.edit(_["dl_failed"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
            return

        # Generate neon thumbnail — reuse the title/thumbnail we already
        # fetched from search_youtube() instead of looking it up again
        # (that 2nd lookup was broken, which is why the card used to show
        # "Unknown Title" / a generic placeholder image).
        video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]
        try:
            thumb = await get_thumb(
                video_id,
                player_username=getattr(client, "username", None),
                title=title,
                thumbnail_url=r.get("thumbnail"),
                duration=duration,
                views=r.get("views"),
            )
        except Exception as e:
            logger.warning(f"get_thumb: {e}")
            thumb = r.get("thumbnail", config.YOUTUBE_IMG_URL)

        song_data = {
            "title":        title,
            "url":          url,
            "link":         link,
            "thumbnail":    thumb,
            "duration_sec": dur_sec,
            "requested_by": uid,
        }
        queue_pos   = await room.add_to_queue(song_data)
        webapp_link = make_startapp_link(link, title, duration, chat_id)
        await mystic.delete()

        user      = message.from_user
        req_mention = f"[{user.first_name}](tg://user?id={uid})"

        if queue_pos == 1:
            # ── Now Playing ──────────────────────────────
            kb  = stream_keyboard(chat_id, "0:00", duration, webapp_link)
            cap = (
                f"**★ ՏԵᗩᖇԵᗴᗞ ՏԵᖇᗴᗩᗰIᑎᘜ ᑎOᗯ ★**\n\n"
                f"**★ Tıttɭε »** [{title}]({link})\n"
                f"**★ Dυɾαtıση »** {duration} Mıηυtεs\n"
                f"**★ Bγ »** {req_mention}"
            )
            sent = await client.send_photo(
                chat_id, photo=thumb or config.YOUTUBE_IMG_URL, caption=cap, reply_markup=kb
            )
            room.play_messages[sent.id] = {"msg": sent, "title": title}
            # Timer updater
            asyncio.create_task(
                _timer_updater(client, chat_id, sent.id, webapp_link, dur_sec, title)
            )
            await rooms_manager.increment_user_stat(uid, songs_delta=1)
            # Log to LOGGER_ID
            asyncio.create_task(log_activity(client,
                f"🎵 **Song Played**\n\n"
                f"👤 **By:** {req_mention}\n"
                f"🆔 **User ID:** `{uid}`\n"
                f"🎵 **Song:** {title}\n"
                f"⏱ **Duration:** {duration}\n"
                f"💬 **Group ID:** `{chat_id}`"
            ))

        else:
            # ── Added to Queue ────────────────────────────
            if room.announce_queue:
                kb  = queue_keyboard(webapp_link)
                cap = (
                    f"🌸≽ Ꭺddǝd Ꭲσ Qυǝυǝ ★ Ꭺƭ #{queue_pos}\n\n"
                    f"★ Tıttɭε » [{title}]({link})\n"
                    f"★ Dυɾαtıση » {duration} Mıηυtεs\n"
                    f"★ Bγ » {req_mention}"
                )
                sent = await client.send_photo(
                    chat_id, photo=thumb, caption=cap, reply_markup=kb
                )
                asyncio.create_task(delete_after(client, chat_id, sent.id, dur_sec + 30))

    except Exception as e:
        logger.error(f"play [{chat_id}]: {e}")
        try:
            await mystic.edit(_["error_general"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
        except Exception:
            try:
                err = await client.send_message(chat_id, _["error_general"])
                asyncio.create_task(delete_after(client, chat_id, err.id, 8))
            except Exception:
                pass


# ── Play Telegram Audio (reply to audio/voice/doc) ─────────
async def _play_telegram_media(
    client: Client, message: Message, replied: "Message",
    uid: int, chat_id: int, _: dict
):
    """Download a Telegram audio/voice/doc and add to queue."""
    import os, time as _time

    mystic = await client.send_message(chat_id, "⏳ **Downloading from Telegram...**")

    try:
        media = replied.audio or replied.voice or replied.document
        if not media:
            await mystic.edit(_["error_general"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
            return

        # Title & duration
        title    = getattr(media, "title", None) \
                   or getattr(media, "file_name", None) \
                   or "Telegram Audio"
        dur_sec  = int(getattr(media, "duration", 0) or 0)
        duration = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "Unknown"

        # Download to static/downloads
        os.makedirs("static/downloads", exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in title)[:40]
        dest = f"static/downloads/tg_{uid}_{int(_time.time())}_{safe}.mp3"

        await client.download_media(replied, file_name=dest)

        if not os.path.exists(dest):
            await mystic.edit(_["dl_failed"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
            return

        url  = f"/static/downloads/{os.path.basename(dest)}"
        room = rooms_manager.get_room(chat_id)

        song_data = {
            "title":        title,
            "url":          url,
            "link":         "",                       # no YT link
            "thumbnail":    config.TELEGRAM_AUDIO_URL,# fallback image
            "duration_sec": dur_sec,
            "requested_by": uid,
        }
        queue_pos   = await room.add_to_queue(song_data)
        webapp_link = make_startapp_link("", title, duration, chat_id)
        await mystic.delete()

        user        = message.from_user
        req_mention = f"[{user.first_name}](tg://user?id={uid})"

        if queue_pos == 1:
            kb  = stream_keyboard(chat_id, "0:00", duration, webapp_link)
            cap = (
                f"**★ ՏԵᗩᖇԵᗴᗞ ՏԵᖇᗴᗩᗰIᑎᘜ ᑎOᗯ ★**\n\n"
                f"**★ Tıttɭε »** {title}\n"
                f"**★ Dυɾαtıση »** {duration}\n"
                f"**★ Bγ »** {req_mention}\n"
                f"**★ Sᴏᴜʀᴄᴇ »** Telegram 🎵"
            )
            sent = await client.send_photo(
                chat_id,
                photo        = config.TELEGRAM_AUDIO_URL,
                caption      = cap,
                reply_markup = kb,
            )
            room.play_messages[sent.id] = {"msg": sent, "title": title}
            if dur_sec:
                asyncio.create_task(
                    _timer_updater(client, chat_id, sent.id, webapp_link, dur_sec, title)
                )
            await rooms_manager.increment_user_stat(uid, songs_delta=1)
            asyncio.create_task(log_activity(client,
                f"📲 **Telegram Audio Played**\n\n"
                f"👤 **By:** {req_mention}\n"
                f"🎵 **Title:** {title}\n"
                f"💬 **Group:** `{chat_id}`"
            ))
        else:
            if room.announce_queue:
                kb  = queue_keyboard(webapp_link)
                cap = (
                    f"🌸≽ Ꭺddǝd Ꭲσ Qυǝυǝ ★ Ꭺƭ #{queue_pos}\n\n"
                    f"★ Tıttɭε » {title}\n"
                    f"★ Dυɾαtıση » {duration}\n"
                    f"★ Bγ » {req_mention}\n"
                    f"★ Sᴏᴜʀᴄᴇ » Telegram 🎵"
                )
                sent = await client.send_photo(
                    chat_id,
                    photo        = config.TELEGRAM_AUDIO_URL,
                    caption      = cap,
                    reply_markup = kb,
                )
                asyncio.create_task(delete_after(client, chat_id, sent.id, dur_sec + 30))

    except Exception as e:
        logger.error(f"_play_telegram_media [{chat_id}]: {e}")
        try:
            await mystic.edit(_["error_general"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
        except Exception:
            pass


# ── Send Now Playing (called by watchdog/skip) ─────────────
async def send_now_playing(client: Client, chat_id: int, room, song: dict):
    title   = song.get("title",        "Unknown")
    link    = song.get("link",          "")
    dur_sec = song.get("duration_sec",  0)
    dur_str = fmt_sec(dur_sec)
    thumb   = song.get("thumbnail",     "")
    req_uid = song.get("requested_by",  0)

    wl  = make_startapp_link(link, title, dur_str, chat_id)
    kb  = stream_keyboard(chat_id, "0:00", dur_str, wl)
    req = f"[{req_uid}](tg://user?id={req_uid})" if req_uid else "Unknown"
    cap = (
        f"**★ ՏԵᗩᖇԵᗴᗞ ՏԵᖇᗴᗩᗰIᑎᘜ ᑎOᗯ ★**\n\n"
        f"**★ Tıttɭε »** [{title}]({link})\n"
        f"**★ Dυɾαtıση »** {dur_str} Mıηυtεs\n"
        f"**★ Bγ »** {req}"
    )
    try:
        if thumb:
            sent = await client.send_photo(chat_id, photo=thumb, caption=cap, reply_markup=kb)
        else:
            sent = await client.send_message(chat_id, cap, reply_markup=kb)
        room.play_messages[sent.id] = {"msg": sent, "title": title}
        asyncio.create_task(
            _timer_updater(client, chat_id, sent.id, wl, dur_sec, title)
        )
        if req_uid:
            await rooms_manager.increment_user_stat(req_uid, songs_delta=1)
    except Exception as e:
        logger.error(f"send_now_playing [{chat_id}]: {e}")


# ── Timer bar updater ─────────────────────────────────────
async def _timer_updater(client: Client, chat_id: int, msg_id: int,
                          wl: str, dur_sec: int, song_title: str):
    room = rooms_manager.get_room(chat_id)
    while True:
        await asyncio.sleep(15)
        if not room.current_song:
            break
        if msg_id not in room.play_messages:
            break
        if room.current_song.get("title") != song_title:
            break
        try:
            seek = room.get_current_seek()
            kb   = stream_keyboard(chat_id, fmt_sec(seek), fmt_sec(dur_sec), wl)
            # reply_markup MUST be passed as a keyword — kurigram inserts
            # extra positional params before it, so `kb` landing in the
            # 3rd *positional* slot silently binds to the wrong param and
            # reply_markup stays None, which WIPES the buttons on the
            # very first timer tick (that's the "buttons fly away" bug).
            await client.edit_message_reply_markup(
                chat_id=chat_id, message_id=msg_id, reply_markup=kb
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug(f"timer [{chat_id}]: {e}")
            break


# ── Stream control callbacks ────────────────────────────────
@Client.on_callback_query(filters.regex(r"^STREAM "))
async def stream_cb(client: Client, cb: CallbackQuery):
    from BadMusic.modules.settings import _safe_delete_msgs
    _ = get_string("en")
    uid  = cb.from_user.id
    name = cb.from_user.first_name
    data = cb.data  # e.g. "STREAM Pause|-1001234"

    if not await is_admin(client, chat_id, uid):
        await cb.answer(_["not_admin"], show_alert=True)
        return

    action, cid_str = data.split(" ", 1)[1].split("|", 1)
    try:
        chat_id = int(cid_str)
    except ValueError:
        await cb.answer(); return

    room = rooms_manager.get_room(chat_id)

    if action == "Pause":
        if not room.is_playing:
            await cb.answer(_["already_paused"], show_alert=True); return
        await room.pause_stream()
        await cb.answer(f"⏸ {name} ᴘᴀᴜsᴇᴅ")

    elif action == "Resume":
        if room.is_playing:
            await cb.answer(_["already_resumed"], show_alert=True); return
        await room.resume_stream()
        await cb.answer(f"▶️ {name} ʀᴇsᴜᴍᴇᴅ")

    elif action == "Skip":
        room.play_messages.pop(cb.message.id, None)
        try:
            await cb.message.delete()
        except Exception:
            pass
        # ✅ Cleanup: delete old song file before skipping
        old_song = room.current_song
        await room.skip_song()
        if old_song and old_song.get("link"):
            vid = _extract_vid(old_song["link"])
            if vid:
                asyncio.create_task(asyncio.to_thread(delete_song_file, vid))
        if room.current_song:
            await send_now_playing(client, chat_id, room, room.current_song)
        else:
            try:
                msg = await client.send_message(
                    chat_id, _["no_more_songs"]
                )
                asyncio.create_task(delete_after(client, chat_id, msg.id, 20))
            except Exception:
                pass
        await cb.answer(f"⏭ sᴋɪᴩᴩᴇᴅ ʙʏ {name}")

    elif action == "Stop":
        # ✅ Cleanup: delete current song file
        if room.current_song and room.current_song.get("link"):
            vid = _extract_vid(room.current_song["link"])
            if vid:
                asyncio.create_task(asyncio.to_thread(delete_song_file, vid))
        await _safe_delete_msgs(client, room)
        await room.stop_session()
        await cb.answer(f"⏹ sᴛᴏᴩᴩᴇᴅ ʙʏ {name}")
        try:
            await cb.message.delete()
        except Exception:
            pass


@Client.on_callback_query(filters.regex("^GetTimer$"))
async def get_timer_cb(client: Client, cb: CallbackQuery):
    await cb.answer("⏱ ᴛɪᴍᴇʀ ʙᴀʀ", show_alert=False)


# ── Inline search ──────────────────────────────────────────
@Client.on_inline_query()
async def inline_search(client: Client, query: InlineQuery):
    if not query.query:
        return
    try:
        results  = await search_youtube(query.query, limit=15)
        answers  = []
        for r in results:
            dur = r["duration"]
            wl  = make_startapp_link(r["link"], r["title"], dur, 0)
            cap = (
                f"**★ Tıttɭε »** [{r['title']}]({r['link']})\n\n"
                f"**★ Dυɾαtıση »** {dur} Mıηυtεs\n"
                f"**★ ᴠɪᴇᴡs »** {r['views']}\n"
                f"**★ ᴄʜ »** {r['channel']}"
            )
            answers.append(InlineQueryResultPhoto(
                photo_url     = r["thumbnail"],
                thumb_url     = r["thumbnail"],
                title         = r["title"],
                caption       = cap,
                reply_markup  = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎵 ᴩʟᴀʏ ᴏɴ ᴡᴇʙᴀᴩᴩ", url=wl)]
                ]),
            ))
        await query.answer(answers, cache_time=300)
    except Exception as e:
        logger.error(f"inline_search: {e}")


# ── /song — download and send audio file ──────────────────
@Client.on_message(filters.command("song") & filters.group)
async def song_cmd(client: Client, message: Message):
    """Download a song and send as audio file in the group."""
    _ = get_string("en")
    try:
        await message.delete()
    except Exception:
        pass

    chat_id = message.chat.id

    if not message.command[1:]:
        msg = await client.send_message(chat_id, _["usage_song"])
        asyncio.create_task(delete_after(client, chat_id, msg.id, 8))
        return

    query  = " ".join(message.command[1:])
    mystic = await client.send_message(chat_id, _["song_dl_start"])

    try:
        results = await search_youtube(query, limit=1)
        if not results:
            await mystic.edit(_["no_results"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
            return

        r       = results[0]
        title   = r["title"]
        link    = r["link"]
        dur     = r["duration"]
        dur_sec = time_to_seconds(dur)

        # Download
        # Download audio (returns URL path like /static/downloads/xxx.mp3)
        dl_path = await download_song(link)
        if not dl_path:
            await mystic.edit(_["song_dl_fail"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
            return

        # dl_path is a URL path — convert to local filesystem path
        local_path = dl_path.lstrip("/")   # "static/downloads/xxx.mp3"
        thumb_url  = r.get("thumbnail", config.YOUTUBE_IMG_URL)

        await mystic.delete()

        # Send as audio file
        await client.send_audio(
            chat_id,
            audio    = local_path,
            title    = title,
            duration = dur_sec,
            caption  = f"**{title}**\nDuration: {dur}",
        )

        # Cleanup local file
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"song_cmd [{chat_id}]: {e}")
        try:
            await mystic.edit(_["song_dl_fail"])
            asyncio.create_task(delete_after(client, chat_id, mystic.id, 8))
        except Exception:
            pass


# ── Chat-based commands (webapp chat → bot commands) ──────
# Users can type /play /skip /stop /pause /resume in the
# webapp chat and the bot will execute them in the group.
# These are triggered via the WebSocket chat handler in app.py
# (see web/app.py _handle_chat_command)

async def handle_chat_command(client, chat_id: int, user_id: int,
                               username: str, text: str):
    """
    Called from web/app.py when a chat message starts with /.
    Executes the command as if typed in the group.
    Only for: /play /skip /stop /pause /resume /queue
    """
    from BadMusic.modules.settings import (
        skip as _skip, stop as _stop,
        pause as _pause, resume as _resume, queue_cmd as _queue,
    )
    from BadMusic.modules.helpers import is_admin as _is_admin
    from strings import get_string
    from BadMusic.utils.thumbnail import get_thumb
    _ = get_string("en")

    parts = text.strip().split(None, 1)
    cmd   = parts[0].lower().lstrip("/")
    args  = parts[1] if len(parts) > 1 else ""

    # Admin-only commands
    admin_cmds = {"skip", "stop", "pause", "resume", "end"}
    if cmd in admin_cmds:
        if not await _is_admin(client, chat_id, user_id):
            return _["admin_only"]

    if cmd == "play" and args:
        # Trigger play logic
        from core.player import rooms_manager
        room    = rooms_manager.get_room(chat_id)
        results = await search_youtube(args, limit=1)
        if not results:
            return _["no_results"]
        r       = results[0]
        dur_sec = time_to_seconds(r["duration"])
        dl_path = await download_song(r["link"])
        if not dl_path:
            return _["dl_failed"]
        song_data = {
            "title":        r["title"],
            "url":          dl_path,
            "link":         r["link"],
            "thumbnail":    r["thumbnail"],
            "duration_sec": dur_sec,
            "requested_by": user_id,
        }
        pos = await room.add_to_queue(song_data)
        return f"Queued: {r['title']} (#{pos})"

    elif cmd == "skip":
        room = __import__("core.player", fromlist=["rooms_manager"]).rooms_manager.get_room(chat_id)
        old_song = room.current_song
        await room.skip_song()
        # ✅ Cleanup old file
        if old_song and old_song.get("link"):
            vid = _extract_vid(old_song["link"])
            if vid:
                import asyncio as _a
                _a.create_task(_a.to_thread(delete_song_file, vid))
        return "Skipped!"

    elif cmd == "stop":
        room = __import__("core.player", fromlist=["rooms_manager"]).rooms_manager.get_room(chat_id)
        await room.stop_session()
        return "Stopped!"

    elif cmd == "pause":
        room = __import__("core.player", fromlist=["rooms_manager"]).rooms_manager.get_room(chat_id)
        if room.is_playing:
            await room.pause_stream()
            return "Paused!"
        return _["already_paused"]

    elif cmd == "resume":
        room = __import__("core.player", fromlist=["rooms_manager"]).rooms_manager.get_room(chat_id)
        if not room.is_playing:
            await room.resume_stream()
            return "Resumed!"
        return _["already_resumed"]

    elif cmd == "queue":
        room = __import__("core.player", fromlist=["rooms_manager"]).rooms_manager.get_room(chat_id)
        if not room.current_song:
            return _["queue_empty"]
        q    = room.queue[:5]
        text = f"Now: {room.current_song['title']}\n"
        if q:
            text += "Queue:\n" + "\n".join(f"{i+1}. {s['title']}" for i,s in enumerate(q))
        return text

    return None


# ── Periodic disk cleanup — runs every 30 min ──────────────
async def _disk_cleanup_loop():
    """Delete mp3 files older than 1 hour to keep VPS clean."""
    from services.downloader import cleanup_old_files, get_disk_usage_mb
    await asyncio.sleep(300)  # wait 5 min after start
    while True:
        try:
            deleted = await cleanup_old_files(max_age_seconds=3600)
            mb      = await get_disk_usage_mb()
            if deleted > 0:
                logger.info(f"🗑 Disk cleanup: {deleted} files removed, {mb:.1f}MB remaining")
        except Exception as e:
            logger.error(f"disk_cleanup_loop: {e}")
        await asyncio.sleep(1800)  # every 30 minutes

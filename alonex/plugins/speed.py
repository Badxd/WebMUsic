# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AloneXMusic

"""
alonex/plugins/speed.py — /speed command.

Deliberately a GROUP-CHAT command only, not a website control: playback
speed changes the real Voice Chat stream (re-encodes via ffmpeg), so it
needs the same admin gate every other transport command uses. The web
room mirrors whatever this sets but can't change it itself.
"""
from pyrogram import filters, types

from alonex import anon, app, db, lang, queue
from alonex.helpers import can_manage_vc


@app.on_message(filters.command(["speed"]) & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _speed(_, m: types.Message):
    if len(m.command) < 2:
        return await m.reply_text(
            m.lang.get("play_speed_usage", "Usage: /speed <0.5 - 2.0>")
        )

    try:
        rate = float(m.command[1])
    except ValueError:
        return await m.reply_text(
            m.lang.get("play_speed_usage", "Usage: /speed <0.5 - 2.0>")
        )

    if not (0.5 <= rate <= 2.0):
        return await m.reply_text(
            m.lang.get("play_speed_range", "Speed must be between 0.5x and 2.0x.")
        )

    if not await db.get_call(m.chat.id):
        return await m.reply_text(m.lang["not_playing"])

    media = queue.get_current(m.chat.id)
    if not media:
        return await m.reply_text(m.lang["not_playing"])

    sent = await m.reply_text(
        m.lang.get("play_speed_changing", "Changing speed to {}x...").format(rate)
    )
    await anon.play_media(m.chat.id, sent, media, seek_time=media.time, rate=rate)
    media.time = media.time or 1
    await sent.edit_text(
        m.lang.get("play_speed_changed", "Speed set to {}x by {}.").format(
            rate, m.from_user.mention
        )
    )

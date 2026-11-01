"""
core/vc_sync.py — bridges core/player.py (the web room) to
core/vc_manager.py (the real Telegram Voice Chat).

Whenever a room's song/queue/pause state changes, RoomsManager calls
the handler below (registered in main.py) so that the SAME audio file
streams both into the group's Voice Chat and into the mini web player
at the same time.
"""
import logging
from typing import Dict, Optional

from core.vc_manager import resolve_local_path, vc_manager

logger = logging.getLogger("VCSync")


async def vc_sync_handler(chat_id: int, action: str, song: Optional[Dict]) -> None:
    if not vc_manager.is_available():
        return  # VC disabled (no STRING_SESSION) — web room still plays fine on its own

    from database import db
    if not db.is_vc_enabled(chat_id):
        # This group has VC switched off (or the global kill-switch is
        # off) — skip real Voice Chat streaming entirely so this group
        # adds zero extra assistant/ffmpeg load. Web room keeps playing
        # on its own as usual.
        return

    if action == "play":
        if not song:
            return
        local_path = resolve_local_path(song.get("url", ""))
        if not local_path:
            logger.warning(f"[VC {chat_id}] no local file for '{song.get('title')}' — VC skipped")
            return
        await vc_manager.join_or_play(chat_id, local_path)

    elif action == "pause":
        await vc_manager.pause(chat_id)

    elif action == "resume":
        await vc_manager.resume(chat_id)

    elif action == "stop":
        await vc_manager.leave(chat_id)

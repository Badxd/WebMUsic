"""
core/vc_manager.py — Real Telegram Voice-Chat streaming (PyTgCalls)

This mirrors what the web room already does (StreamState / RoomQueue)
but pushes the SAME audio file into the group's actual Voice Chat
through an assistant (userbot) account, using py-tgcalls. The web
room and the VC always carry the same song — this module never makes
its own decisions about what to play, it only mirrors core/player.py.
"""
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger("VCManager")

PYTGCALLS_AVAILABLE = False
try:
    import pytgcalls as _ptgc
    from pytgcalls.exceptions import NoActiveGroupCall
    from pytgcalls.types import AudioQuality, MediaStream
    PYTGCALLS_AVAILABLE = True
except ImportError:
    NoActiveGroupCall = Exception
    logger.warning("py-tgcalls not installed — Voice Chat streaming disabled.")


def resolve_local_path(url: str) -> Optional[str]:
    """Song dicts store a web path like '/static/downloads/x.mp3' — turn
    that into the real filesystem path PyTgCalls needs to stream."""
    if not url:
        return None
    path = url.lstrip("/")
    return path if os.path.exists(path) else None


class VCManager:
    def __init__(self):
        self._call = None
        self._ready = False
        self._vc_active: Dict[int, bool] = {}
        self._paused: Dict[int, bool] = {}

    def setup(self, call_py) -> None:
        """Wire in the already-created PyTgCalls instance (BadMusic.call_py)."""
        if not PYTGCALLS_AVAILABLE or call_py is None:
            self._ready = False
            return
        self._call = call_py
        self._ready = True
        logger.info("VCManager ready ✅")

    async def start(self) -> None:
        if not self._ready or not self._call:
            return
        try:
            await self._call.start()
            logger.info("PyTgCalls started ✅")
        except Exception as e:
            logger.error(f"PyTgCalls.start(): {e}")
            self._ready = False

    async def join_or_play(self, chat_id: int, audio_file: str) -> bool:
        """Join the VC (or switch track if already in it) and stream audio_file."""
        if not self.is_available():
            return False
        if not audio_file or not os.path.exists(audio_file):
            logger.warning(f"[VC {chat_id}] file not found: {audio_file}")
            return False
        try:
            await self._call.play(
                chat_id, MediaStream(audio_file, audio_parameters=AudioQuality.HIGH)
            )
            self._vc_active[chat_id] = True
            self._paused[chat_id] = False
            return True
        except NoActiveGroupCall:
            logger.warning(f"[VC {chat_id}] no active group call — start a VC in the group first.")
            return False
        except Exception as e:
            logger.error(f"[VC {chat_id}] join_or_play: {e}")
            return False

    async def pause(self, chat_id: int) -> bool:
        if not self.is_available() or not self._vc_active.get(chat_id):
            return False
        try:
            await self._call.pause(chat_id)
            self._paused[chat_id] = True
            return True
        except Exception as e:
            logger.warning(f"[VC {chat_id}] pause: {e}")
            return False

    async def resume(self, chat_id: int) -> bool:
        if not self.is_available() or not self._vc_active.get(chat_id):
            return False
        try:
            await self._call.resume(chat_id)
            self._paused[chat_id] = False
            return True
        except Exception as e:
            logger.warning(f"[VC {chat_id}] resume: {e}")
            return False

    async def leave(self, chat_id: int) -> bool:
        if not self.is_available():
            return False
        try:
            await self._call.leave_call(chat_id)
        except Exception as e:
            logger.debug(f"[VC {chat_id}] leave: {e}")
        self._vc_active.pop(chat_id, None)
        self._paused.pop(chat_id, None)
        return True

    def is_vc_active(self, chat_id: int) -> bool:
        return bool(self._vc_active.get(chat_id))

    def is_available(self) -> bool:
        return self._ready and PYTGCALLS_AVAILABLE and self._call is not None


vc_manager = VCManager()

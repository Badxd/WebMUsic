"""
core/player.py — MusicRoom (per-group state) + RoomsManager (global registry)
"""
import asyncio
import logging
import os
import shutil
from typing import Any, Callable, Dict, List, Optional, Set

from .queue  import RoomQueue
from .stream import StreamState

logger = logging.getLogger("Player")


class MusicRoom:
    """Holds all playback state for a single Telegram group."""

    def __init__(self, chat_id: int):
        self.chat_id      = chat_id
        self.current_song: Optional[Dict] = None
        self._queue       = RoomQueue()
        self._stream      = StreamState()
        self.listeners:    List[Any]          = []
        self.listener_info: Dict[str, Dict]   = {}
        self.play_messages: Dict[int, Any]    = {}   # msg_id → {msg, title}
        self.announce_join  = True
        self.announce_queue = True
        self._advancing     = False
        self._on_change: Optional[Callable]   = None
        self._vc_sync: Optional[Callable]     = None   # set by RoomsManager → VC (Voice Chat)

    # ── Public stream properties ──────────────────────────
    @property
    def is_playing(self) -> bool:
        return self._stream.is_playing

    @property
    def seek_time(self) -> float:
        return self._stream.seek_time

    @seek_time.setter
    def seek_time(self, v: float):
        self._stream.seek_time = v

    @property
    def last_update_time(self) -> float:
        return self._stream.last_update_time

    @last_update_time.setter
    def last_update_time(self, v: float):
        self._stream.last_update_time = v

    @property
    def current_song_duration(self) -> int:
        return self._stream.duration

    @property
    def queue(self) -> List[Dict]:
        return self._queue.as_list()

    def get_current_seek(self) -> float:
        return self._stream.get_seek()

    def is_song_finished(self) -> bool:
        return not self._advancing and self._stream.is_finished()

    # ── Callbacks ─────────────────────────────────────────
    def set_on_change_callback(self, cb: Callable):
        self._on_change = cb

    def set_vc_sync_callback(self, cb: Callable):
        self._vc_sync = cb

    async def _notify(self):
        if self._on_change:
            if asyncio.iscoroutinefunction(self._on_change):
                await self._on_change(self.chat_id)
            else:
                self._on_change(self.chat_id)

    async def _sync_vc(self, action: str):
        """Mirror this room's state into the real Telegram Voice Chat.
        action: 'play' | 'pause' | 'resume' | 'stop'
        """
        if not self._vc_sync:
            return
        try:
            await self._vc_sync(self.chat_id, action, self.current_song)
        except Exception as e:
            logger.warning(f"VC sync [{self.chat_id}] {action}: {e}")

    # ── Queue operations ──────────────────────────────────
    async def add_to_queue(self, song: Dict) -> int:
        """
        Returns 1 if playing now, N if queued at position N.
        """
        if self.current_song is None:
            self.current_song          = song
            self._stream.duration      = song.get("duration_sec", 0)
            self._stream.play(seek=0.0)
            pos = 1
        else:
            self._queue.add(song)
            pos = self._queue.count + 1
        await self._notify()
        if pos == 1:
            await self._sync_vc("play")
        return pos

    async def skip_song(self):
        next_song = self._queue.pop_next()
        if next_song:
            self.current_song          = next_song
            self._stream.duration      = next_song.get("duration_sec", 0)
            self._stream.play(seek=0.0)
        else:
            self.current_song = None
            self._stream.reset()
        self._advancing = False
        await self._notify()
        await self._sync_vc("play" if next_song else "stop")

    async def stop_session(self):
        self._reset_all()
        await self._notify()
        await self._sync_vc("stop")

    async def pause_stream(self):
        if not self._stream.is_playing:
            return
        self._stream.pause()
        await self._notify()
        await self._sync_vc("pause")

    async def resume_stream(self):
        if self._stream.is_playing:
            return
        self._stream.resume()
        await self._notify()
        await self._sync_vc("resume")

    def _reset_all(self):
        self.current_song   = None
        self._queue.clear()
        self._stream.reset()
        self.play_messages  = {}
        self._advancing     = False


class RoomsManager:
    """Global registry of all active MusicRooms."""

    def __init__(self):
        self.rooms:   Dict[int, MusicRoom] = {}
        self.owner_id: Optional[int]       = None
        self._broadcast_cb: Optional[Callable] = None
        self._vc_sync_cb: Optional[Callable]   = None
        # Reference to DB set after initialize()
        self._db = None

    def set_broadcast_callback(self, cb: Callable):
        self._broadcast_cb = cb

    def set_vc_sync_callback(self, cb: Callable):
        """cb(chat_id, action, song) — called to mirror room state into
        the real Telegram Voice Chat. Wired from main.py once the
        assistant + PyTgCalls are ready."""
        self._vc_sync_cb = cb
        for r in self.rooms.values():
            r.set_vc_sync_callback(cb)

    def get_room(self, chat_id: int) -> MusicRoom:
        if chat_id not in self.rooms:
            r = MusicRoom(chat_id)
            r.set_on_change_callback(self._on_room_change)
            if self._vc_sync_cb:
                r.set_vc_sync_callback(self._vc_sync_cb)
            self.rooms[chat_id] = r
        return self.rooms[chat_id]

    async def _on_room_change(self, chat_id: int):
        if self._broadcast_cb:
            await self._broadcast_cb(chat_id)

    def is_admin(self, user_id: int) -> bool:
        from database import db
        return db.is_admin(user_id, self.owner_id or 0)

    async def initialize(self):
        from database import db
        self._db = db
        await db.connect()
        if self.owner_id:
            pass  # owner_id set from config

    # ── Convenience wrappers (keep same API as old manager) ─
    async def increment_user_stat(self, user_id: int, songs_delta=0, seconds_delta=0):
        from database import db
        await db.increment_stat(user_id, songs=songs_delta, seconds=seconds_delta)

    async def get_user_stats(self, user_id: int) -> Dict:
        from database import db
        return await db.get_stats(user_id)

    @property
    def admins(self) -> Set[int]:
        from database import db
        return db._admins

    @property
    def blacklisted_users(self) -> Set[int]:
        from database import db
        return db._blacklisted

    async def auth_user(self, uid: int):
        from database import db
        await db.add_admin(uid)

    async def unauth_user(self, uid: int):
        from database import db
        await db.remove_admin(uid)

    async def blacklist_user(self, uid: int):
        from database import db
        await db.blacklist(uid)

    async def unblacklist_user(self, uid: int):
        from database import db
        await db.unblacklist(uid)

    def clean_downloads(self) -> bool:
        d = "static/downloads"
        if os.path.exists(d):
            shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)
            return True
        return False


# Single global instance
rooms_manager = RoomsManager()

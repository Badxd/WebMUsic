# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AloneXMusic

"""
alonex/web/state.py — tiny, additive state for the mini web "room".

Deliberately does NOT touch alonex.helpers.Queue or Media/Track — this
only tracks what the website needs on top of what already exists:
  - a wall-clock position per chat (AloneX's own `media.time` is only
    set once at play-start and on manual /seek, it isn't continuously
    updated — fine for the bot's own UI, not enough for a live
    progress bar on the website)
  - which websocket connections are listening to which chat
"""
import time
from typing import Dict, List, Optional, Set

from fastapi import WebSocket


class RoomClock:
    def __init__(self):
        self.start_wall: float = 0.0
        self.offset: float = 0.0      # seconds already elapsed before this (re)start
        self.playing: bool = False
        self.duration: int = 0

    def start(self, offset: float = 0.0, duration: int = 0):
        self.start_wall = time.time()
        self.offset = max(0.0, offset)
        self.duration = duration
        self.playing = True

    def pause(self):
        if self.playing:
            self.offset = self.position()
            self.playing = False

    def resume(self):
        if not self.playing:
            self.start_wall = time.time()
            self.playing = True

    def position(self) -> float:
        if self.playing:
            raw = self.offset + (time.time() - self.start_wall)
            return min(raw, float(self.duration)) if self.duration > 0 else raw
        return self.offset

    def reset(self):
        self.start_wall = 0.0
        self.offset = 0.0
        self.playing = False
        self.duration = 0


class RoomState:
    def __init__(self):
        self.clocks: Dict[int, RoomClock] = {}
        self.listeners: Dict[int, Set[WebSocket]] = {}
        self._chat_title_cache: Dict[int, tuple] = {}  # chat_id -> (title, fetched_at)

    def clock(self, chat_id: int) -> RoomClock:
        if chat_id not in self.clocks:
            self.clocks[chat_id] = RoomClock()
        return self.clocks[chat_id]

    def add_listener(self, chat_id: int, ws: WebSocket):
        self.listeners.setdefault(chat_id, set()).add(ws)

    def remove_listener(self, chat_id: int, ws: WebSocket):
        if chat_id in self.listeners:
            self.listeners[chat_id].discard(ws)

    def listener_count(self, chat_id: int) -> int:
        return len(self.listeners.get(chat_id, ()))


room_state = RoomState()

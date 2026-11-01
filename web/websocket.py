# Copyright (C) 2024 by Badhacker98@Github
"""
web/websocket.py
_build_state: returns real-time seek so late joiners sync correctly.
"""
import logging
from core.player import rooms_manager

logger = logging.getLogger("WebSocket")


def _build_state(chat_id: int) -> dict:
    """
    Build full room state for broadcasting.
    seek_time is always the LIVE calculated position —
    so a user joining mid-song picks up exactly where
    the song is, not from the beginning.
    """
    room = rooms_manager.get_room(chat_id)
    return {
        "type":           "state_update",
        "chat_id":        chat_id,
        "current_song":   room.current_song,
        "is_playing":     room.is_playing,
        "seek_time":      room.get_current_seek(),
        "listeners":      list(room.listener_info.values()),
        "queue":          room.queue,
        "bass_config":    getattr(room, "bass_config",   {"level": "off", "gain": 0, "freq": 60}),
        # Autoplay state — sent to frontend
        "autoplay":       getattr(room, "_autoplay_enabled", False),
        "autoplay_query": getattr(room, "_autoplay_query",   ""),
    }
    

"""
core/stream.py — Playback state tracker
"""
import asyncio
import time as _time
from typing import Optional


def _now() -> float:
    """Safe monotonic time — works inside or outside async context."""
    try:
        loop = asyncio.get_running_loop()
        return loop.time()
    except RuntimeError:
        return _time.monotonic()


class StreamState:
    def __init__(self):
        self.is_playing:       bool  = False
        self.seek_time:        float = 0.0
        self.last_update_time: float = 0.0
        self.duration:         int   = 0

    def get_seek(self) -> float:
        if self.is_playing and self.last_update_time > 0:
            raw = self.seek_time + (_now() - self.last_update_time)
            return min(raw, float(self.duration)) if self.duration > 0 else max(0.0, raw)
        return max(0.0, self.seek_time)

    def is_finished(self) -> bool:
        if not self.is_playing or self.duration <= 0:
            return False
        return self.get_seek() >= self.duration - 1.5

    def play(self, seek: Optional[float] = None):
        if seek is not None:
            self.seek_time = seek
        self.last_update_time = _now()
        self.is_playing       = True

    def pause(self):
        self.seek_time        = self.get_seek()
        self.last_update_time = _now()
        self.is_playing       = False

    def resume(self):
        self.last_update_time = _now()
        self.is_playing       = True

    def seek(self, position: float):
        self.seek_time        = position
        self.last_update_time = _now()

    def reset(self):
        self.is_playing       = False
        self.seek_time        = 0.0
        self.last_update_time = 0.0
        self.duration         = 0
        

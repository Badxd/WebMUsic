"""
core/queue.py — Queue management for a single music room
"""
from typing import Dict, List, Optional


class RoomQueue:
    def __init__(self):
        self._queue: List[Dict] = []

    @property
    def items(self) -> List[Dict]:
        return list(self._queue)

    @property
    def count(self) -> int:
        return len(self._queue)

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def add(self, song: Dict) -> int:
        """Add song to queue. Returns 0-based index (0 = first in queue)."""
        self._queue.append(song)
        return len(self._queue) - 1

    def pop_next(self) -> Optional[Dict]:
        """Remove and return next song, or None if empty."""
        return self._queue.pop(0) if self._queue else None

    def clear(self):
        self._queue.clear()

    def as_list(self) -> List[Dict]:
        return list(self._queue)

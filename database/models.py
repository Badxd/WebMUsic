"""
database/models.py — Data shape definitions (TypedDicts for clarity)
Not enforced at runtime, just for IDE hints and documentation.
"""
from typing import Optional
from typing_extensions import TypedDict


class SongDict(TypedDict):
    title:        str
    url:          str          # local /static/downloads/xxx.mp3
    link:         str          # original YouTube URL
    thumbnail:    str          # permanent thumbnail URL
    duration_sec: int
    requested_by: int          # Telegram user_id


class ListenerInfo(TypedDict):
    username: str
    user_id:  int
    is_admin: bool


class RoomState(TypedDict):
    chat_id:      int
    current_song: Optional[SongDict]
    is_playing:   bool
    seek_time:    float
    queue:        list
    listeners:    list

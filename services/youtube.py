"""
services/youtube.py — YouTube search wrapper (yt-dlp based)

Previously this used `youtube-search-python`, an unmaintained scraper
library whose internal HTTP client (httpx) breaks on newer httpx
versions with: "post() got an unexpected keyword argument 'proxies'"
(httpx removed `proxies` in 0.28). It also needs NO API key at all —
yt-dlp just reads YouTube's public search/watch pages, the same way
it already does for every other yt-dlp based bot.
"""
import asyncio
import logging
from typing import Dict, List

import yt_dlp

logger = logging.getLogger("YouTube")

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "noplaylist": True,
    "default_search": "ytsearch",
    "socket_timeout": 15,
}


def _fmt_duration(seconds) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return "0:00"
    if seconds <= 0:
        return "0:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _blocking_search(query: str, limit: int) -> List[Dict]:
    out: List[Dict] = []
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = (info or {}).get("entries") or []
        for e in entries:
            if not e:
                continue
            vid_id = e.get("id", "")
            if not vid_id:
                continue
            out.append({
                "id":        vid_id,
                "title":     e.get("title", "Unknown"),
                "link":      f"https://www.youtube.com/watch?v={vid_id}",
                "duration":  _fmt_duration(e.get("duration")),
                # ✅ Permanent URL — never expires, doesn't need an API key
                "thumbnail": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                "views":     str(e.get("view_count") or "?"),
                "channel":   e.get("channel") or e.get("uploader") or "?",
                "published": e.get("upload_date") or "?",
            })
    return out


async def search_youtube(query: str, limit: int = 1) -> List[Dict]:
    """
    Search YouTube and return list of result dicts.
    Each dict has: title, link, duration, thumbnail, views, channel, published, id
    Runs the (blocking) yt-dlp extraction in a thread so it never
    stalls the bot's event loop.
    """
    try:
        return await asyncio.to_thread(_blocking_search, query, limit)
    except Exception as e:
        logger.error(f"search_youtube: {e}")
        return []

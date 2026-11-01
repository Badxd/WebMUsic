"""
services/youtube.py — YouTube search wrapper
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("YouTube")


async def search_youtube(query: str, limit: int = 1) -> List[Dict]:
    """
    Search YouTube and return list of result dicts.
    Each dict has: title, link, duration, thumbnail, views, channel, published, id
    thumbnail is ALWAYS the permanent img.youtube.com URL (never expires).
    """
    try:
        from youtubesearchpython import VideosSearch
        results = VideosSearch(query, limit=limit).result()["result"]
        out = []
        for r in results:
            vid_id = r.get("id", "")
            out.append({
                "id":        vid_id,
                "title":     r.get("title", "Unknown"),
                "link":      r.get("link",  ""),
                "duration":  r.get("duration") or "0:00",
                # ✅ Permanent URL — search result URLs expire with query params
                "thumbnail": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                "views":     r.get("viewCount", {}).get("short", "?"),
                "channel":   r.get("channel",   {}).get("name",  "?"),
                "published": r.get("publishedTime", "?"),
            })
        return out
    except Exception as e:
        logger.error(f"search_youtube: {e}")
        return []

"""
web/routes.py — All REST API route handlers  (FULL FIXED v2)
New:  /profile  /profile/update  /friends  /autoplay  /autoplay/next
      /notifications  /room_expired  /shared_playlist
"""
import logging
import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.player import rooms_manager
from database    import db
from services.downloader import download_song, extract_video_id, get_thumbnail_url, time_to_seconds
from services.youtube    import search_youtube

logger = logging.getLogger("Routes")
router = APIRouter()


# ─────────────────────────────────────────────────────────
#  /status
# ─────────────────────────────────────────────────────────
@router.get("/status")
async def get_status(chat_id: int = 0):
    room = rooms_manager.get_room(chat_id)
    song = room.current_song
    # Auto-refresh expired URL
    if song and song.get("link") and not song.get("url"):
        try:
            new_url = await download_song(song["link"])
            if new_url:
                song["url"] = new_url
        except Exception:
            pass
    return {
        "current_song":    song,
        "is_playing":      room.is_playing,
        "seek_time":       room.get_current_seek(),
        "queue":           room.queue,
        "listeners_count": len(room.listeners),
        "listeners":       list(room.listener_info.values()),
        "autoplay":        getattr(room, "_autoplay_enabled", False),
        "autoplay_query":  getattr(room, "_autoplay_query", ""),
    }


# ─────────────────────────────────────────────────────────
#  /play_song
# ─────────────────────────────────────────────────────────
@router.post("/play_song")
async def play_song(
    link:     str,
    title:    str = "Unknown",
    duration: str = "0:00",
    chat_id:  int = 0,
    user_id:  int = 0,
):
    try:
        video_id = extract_video_id(link)
        if not video_id:
            return JSONResponse(status_code=400, content={"error": "Invalid link"})

        room = rooms_manager.get_room(chat_id)

        if room.current_song and room.current_song.get("link") == link:
            return {"status": "already_playing", "url": room.current_song.get("url",""), "queue_position":1}
        for i, q in enumerate(room.queue):
            if q.get("link") == link:
                return {"status": "already_queued", "url": q.get("url",""), "queue_position": i+2}

        url = await download_song(link)
        if not url:
            return JSONResponse(status_code=500, content={"error": "Download failed"})

        song_data = {
            "title":        title,
            "url":          url,
            "link":         link,
            "thumbnail":    get_thumbnail_url(video_id),
            "duration_sec": time_to_seconds(duration),
            "requested_by": user_id,
            "queued_at":    datetime.datetime.utcnow().isoformat(),
        }
        queue_pos = await room.add_to_queue(song_data)
        if queue_pos == 1 and user_id:
            await rooms_manager.increment_user_stat(user_id, songs_delta=1)
        return {"status": "success", "url": url, "queue_position": queue_pos}

    except Exception as e:
        logger.error(f"play_song: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────
#  /refresh_url  — called when audio 404s
# ─────────────────────────────────────────────────────────
@router.get("/refresh_url")
async def refresh_url(link: str, chat_id: int = 0):
    try:
        url = await download_song(link)
        if not url:
            return JSONResponse(status_code=500, content={"error": "Re-download failed"})
        room = rooms_manager.get_room(chat_id)
        if room.current_song and room.current_song.get("link") == link:
            room.current_song["url"] = url
        return {"status": "ok", "url": url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────
#  /room_expired — when link expired and room empty
# ─────────────────────────────────────────────────────────
@router.get("/room_expired")
async def room_expired(chat_id: int = 0):
    """Called by frontend when song expired and no current song found."""
    room = rooms_manager.get_room(chat_id)
    ap   = await db.get_autoplay(chat_id)
    if ap.get("enabled") and ap.get("query"):
        results = await search_youtube(ap["query"], limit=5)
        if results:
            return {"status": "autoplay_available", "results": results}
    return {"status": "empty", "message": "Room empty. Use /play in group to start!"}


# ─────────────────────────────────────────────────────────
#  /skip_song  /end_session
# ─────────────────────────────────────────────────────────
@router.post("/skip_song")
async def skip_song(chat_id: int = 0):
    await rooms_manager.get_room(chat_id).skip_song()
    return {"status": "success"}


@router.post("/end_session")
async def end_session(chat_id: int = 0):
    await rooms_manager.get_room(chat_id).stop_session()
    return {"status": "success"}


# ─────────────────────────────────────────────────────────
#  /user_stats  (legacy keep)
# ─────────────────────────────────────────────────────────
@router.get("/user_stats")
async def user_stats(user_id: int = 0):
    stats = await rooms_manager.get_user_stats(user_id)
    room_count = sum(
        1 for room in rooms_manager.rooms.values()
        if any(info.get("user_id") == user_id for info in room.listener_info.values())
    )
    stats["rooms"] = room_count
    return stats


# ─────────────────────────────────────────────────────────
#  /profile  — full rich profile
# ─────────────────────────────────────────────────────────
@router.get("/profile")
async def get_profile(user_id: int = 0):
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "user_id required"})
    prof  = await db.get_profile(user_id)
    stats = await db.get_stats(user_id)

    # ✅ FIX: Remove MongoDB _id (ObjectId) — not JSON serializable
    prof.pop("_id", None)

    prof["total_songs"]   = stats.get("songs",   prof.get("total_songs",   0))
    prof["total_seconds"] = stats.get("seconds", prof.get("total_seconds", 0))

    # online friends
    online_ids = set()
    for room in rooms_manager.rooms.values():
        for info in room.listener_info.values():
            online_ids.add(info.get("user_id"))
    friends = prof.get("friends", [])
    for f in friends:
        f["online"] = f.get("id") in online_ids
    prof["friends"] = friends
    return prof


@router.post("/profile/update")
async def update_profile(
    user_id:     int = 0,
    bio:         str = None,
    theme_color: str = None,
):
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "user_id required"})
    upd = {}
    if bio         is not None: upd["bio"]         = bio[:120]
    if theme_color is not None: upd["theme_color"] = theme_color
    await db.update_profile(user_id, upd)
    return {"status": "ok"}


@router.post("/profile/log_session")
async def log_session(
    user_id:     int   = 0,
    song_title:  str   = "",
    artist:      str   = "",
    duration_sec:int   = 0,
    bass_level:  str   = "off",
    speed:       float = 1.0,
    chat_id:     int   = 0,
):
    if not user_id:
        return {"status": "skip"}
    hour = datetime.datetime.now().hour
    await db.log_listen_session(
        user_id, song_title, artist, duration_sec, hour, bass_level, speed, chat_id)
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────
#  /friends
# ─────────────────────────────────────────────────────────
@router.post("/friends/add")
async def add_friend(user_id: int = 0, friend_id: int = 0, friend_name: str = ""):
    if not user_id or not friend_id:
        return JSONResponse(status_code=400, content={"error": "user_id and friend_id required"})
    ok = await db.add_friend(user_id, friend_id, friend_name)
    return {"status": "ok" if ok else "no_db"}


@router.post("/friends/remove")
async def remove_friend(user_id: int = 0, friend_id: int = 0):
    ok = await db.remove_friend(user_id, friend_id)
    return {"status": "ok" if ok else "no_db"}


@router.get("/friends")
async def get_friends(user_id: int = 0):
    friends = await db.get_friends(user_id)
    online_ids = set()
    for room in rooms_manager.rooms.values():
        for info in room.listener_info.values():
            online_ids.add(info.get("user_id"))
    for f in friends:
        f["online"] = f.get("id") in online_ids
    return {"friends": friends}


# ─────────────────────────────────────────────────────────
#  /autoplay
# ─────────────────────────────────────────────────────────
@router.get("/autoplay")
async def get_autoplay(chat_id: int = 0):
    return await db.get_autoplay(chat_id)


@router.post("/autoplay/set")
async def set_autoplay(chat_id: int = 0, enabled: bool = True, query: str = ""):
    room = rooms_manager.get_room(chat_id)
    room._autoplay_enabled = enabled
    room._autoplay_query   = query
    await db.set_autoplay(chat_id, enabled, query)
    return {"status": "ok", "enabled": enabled, "query": query}


@router.get("/autoplay/next")
async def autoplay_next(chat_id: int = 0, current_title: str = ""):
    """Fetch next related song for autoplay — never repeats current or queued songs."""
    ap = await db.get_autoplay(chat_id)
    if not ap.get("enabled"):
        return {"status": "disabled"}

    seed_query = ap.get("query", "").strip()
    room       = rooms_manager.get_room(chat_id)

    # ✅ FIX: Build played set to avoid repeats
    played = set()
    if room.current_song:
        played.add(room.current_song.get("link", ""))
        played.add(room.current_song.get("title", "").lower())
    for q in room.queue:
        played.add(q.get("link", ""))
        played.add(q.get("title", "").lower())

    # ✅ FIX: Use multiple search strategies to get variety
    # Strategy 1: seed query
    # Strategy 2: current song title (for related songs)
    # Strategy 3: generic popular based on seed genre

    search_queries = []
    if seed_query:
        search_queries.append(seed_query)                        # e.g. "Sidhu Moosewala"
        search_queries.append(seed_query + " new songs 2024")   # newer songs
    if current_title:
        # Extract artist name (before " - " or first 2 words)
        artist = current_title.split(" - ")[0].strip()
        if artist and artist.lower() not in seed_query.lower():
            search_queries.append(artist + " songs")

    if not search_queries:
        search_queries = ["popular punjabi songs 2024"]

    import random
    # Shuffle to get variety across calls
    random.shuffle(search_queries)

    for query in search_queries:
        results = await search_youtube(query, limit=10)
        # Filter out already played / queued
        candidates = [
            r for r in results
            if r.get("link") not in played
            and r.get("title", "").lower() not in played
        ]
        if candidates:
            # Pick randomly from top 3 to add variety
            pick = random.choice(candidates[:3])
            return {"status": "ok", "song": pick}

    return {"status": "no_results"}


# ─────────────────────────────────────────────────────────
#  /favorites
# ─────────────────────────────────────────────────────────
@router.get("/favorites")
async def get_favorites(user_id: int = 0):
    if not user_id:
        return {"favorites": []}
    return {"favorites": await db.get_favorites(user_id)}


@router.post("/favorites")
async def save_favorite(
    user_id:      int = 0,
    link:         str = "",
    title:        str = "",
    thumbnail:    str = "",
    duration_sec: int = 0,
):
    if not user_id or not link:
        return JSONResponse(status_code=400, content={"error": "user_id and link required"})
    ok = await db.add_favorite(user_id, {
        "title": title, "link": link,
        "thumbnail": thumbnail, "duration_sec": duration_sec,
    })
    return {"status": "ok" if ok else "no_db"}


@router.delete("/favorites")
async def delete_favorite(user_id: int = 0, link: str = ""):
    if not user_id or not link:
        return JSONResponse(status_code=400, content={"error": "required"})
    ok = await db.remove_favorite(user_id, link)
    return {"status": "ok" if ok else "no_db"}


# ─────────────────────────────────────────────────────────
#  /queue_favorite
# ─────────────────────────────────────────────────────────
@router.post("/queue_favorite")
async def queue_favorite(
    link:     str,
    title:    str = "",
    duration: str = "0:00",
    chat_id:  int = 0,
    user_id:  int = 0,
):
    try:
        video_id = extract_video_id(link)
        if not video_id:
            return JSONResponse(status_code=400, content={"error": "Invalid link"})
        room = rooms_manager.get_room(chat_id)
        if room.current_song and room.current_song.get("link") == link:
            return {"status": "already_playing", "queue_position": 1}
        for i, q in enumerate(room.queue):
            if q.get("link") == link:
                return {"status": "already_queued", "queue_position": i+2}
        url = await download_song(link)
        if not url:
            return JSONResponse(status_code=500, content={"error": "Download failed"})
        song_data = {
            "title":        title or "Unknown",
            "url":          url,
            "link":         link,
            "thumbnail":    get_thumbnail_url(video_id),
            "duration_sec": time_to_seconds(duration),
            "requested_by": user_id,
        }
        pos = await room.add_to_queue(song_data)
        return {"status": "success", "queue_position": pos}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────
#  /shared_playlist
# ─────────────────────────────────────────────────────────
@router.get("/shared_playlist/{playlist_id}")
async def get_shared_playlist(playlist_id: str):
    if db.db is None:
        return JSONResponse(status_code=503, content={"error": "No DB"})
    try:
        doc = await db.db.shared_playlists.find_one({"id": playlist_id})
        if not doc:
            return JSONResponse(status_code=404, content={"error": "Not found"})
        doc.pop("_id", None)
        return doc
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/shared_playlist")
async def create_shared_playlist(
    user_id:  int = 0,
    name:     str = "My Playlist",
    songs:    str = "[]",  # JSON string
):
    if db.db is None:
        return JSONResponse(status_code=503, content={"error": "No DB"})
    import json, secrets
    try:
        songs_list = json.loads(songs)[:50]
        pid = secrets.token_urlsafe(8)
        await db.db.shared_playlists.insert_one({
            "id": pid, "user_id": user_id, "name": name,
            "songs": songs_list,
            "created_at": datetime.datetime.utcnow().isoformat()
        })
        return {"status": "ok", "playlist_id": pid, "share_url": f"/shared_playlist/{pid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─────────────────────────────────────────────────────────
#  /notifications
# ─────────────────────────────────────────────────────────
_notif_store: dict = {}  # user_id -> [notif, ...]

@router.get("/notifications")
async def get_notifications(user_id: int = 0):
    notifs = _notif_store.pop(user_id, [])
    return {"notifications": notifs}


def push_notification(user_id: int, msg: str, ntype: str = "info"):
    if user_id not in _notif_store:
        _notif_store[user_id] = []
    _notif_store[user_id].append({"message": msg, "type": ntype,
                                   "ts": datetime.datetime.utcnow().isoformat()})
    _notif_store[user_id] = _notif_store[user_id][-10:]

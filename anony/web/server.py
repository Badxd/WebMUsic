# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

"""
anony/web/server.py — the mini "room" webapp.

Read-mostly by design: AnonX's own queue/calls/db stay the single
source of truth. This layer only (a) reports that state live over a
websocket and (b) forwards a handful of admin-gated controls into the
exact same functions the /pause /resume /skip commands already call —
nothing here duplicates AnonX's playback logic.

Speed is intentionally NOT controllable from here — see
anony/plugins/speed.py: it's a group-chat command only.
"""
import logging
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("anony.web")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _media_to_dict(media, chat_id: int) -> dict:
    from anony.web.state import room_state
    clock = room_state.clock(chat_id)
    thumbnail = getattr(media, "thumbnail", None)
    return {
        "title":        media.title or "Unknown",
        "url":          media.url,
        "duration_sec": media.duration_sec or 0,
        "thumbnail":    thumbnail,
        "requested_by": media.user,
        "seek":         clock.position(),
        "playing":      clock.playing,
    }


async def _chat_title(chat_id: int) -> str:
    """Group name shown on the join screen — like Playeon. Cached for
    a few minutes so every websocket connect doesn't re-hit Telegram."""
    from anony import app
    from anony.web.state import room_state

    cached = room_state._chat_title_cache.get(chat_id)
    if cached and time.time() - cached[1] < 300:
        return cached[0]
    try:
        chat = await app.get_chat(chat_id)
        title = chat.title or chat.first_name or "Room"
    except Exception as e:
        logger.debug(f"get_chat({chat_id}): {e}")
        title = "Room"
    room_state._chat_title_cache[chat_id] = (title, time.time())
    return title


async def build_state(chat_id: int) -> dict:
    from anony import queue, db
    from anony.web.state import room_state

    media = queue.get_current(chat_id)
    is_live = bool(await db.get_call(chat_id))
    return {
        "chat_id":   chat_id,
        "chat_name": await _chat_title(chat_id),
        "active":    is_live and media is not None,
        "song":      _media_to_dict(media, chat_id) if (is_live and media) else None,
        "queue": [
            {"title": m.title, "duration": m.duration, "requested_by": m.user}
            for m in queue.get_queue(chat_id)
        ][:20],
        "listeners": room_state.listener_count(chat_id),
    }


async def broadcast(chat_id: int):
    """Call this after anything changes the room — play/pause/resume/
    skip/stop — so every open tab updates immediately. Each listener
    gets the same room state, PLUS their own is_admin flag (computed
    once at connect time — see ws_room below) so the website only
    shows transport controls to actual group admins, same gate the
    POST /api/control endpoint enforces."""
    from anony.web.state import room_state
    listeners = list(room_state.listeners.get(chat_id, ()))
    if not listeners:
        return
    state = await build_state(chat_id)
    dead = []
    for ws in listeners:
        try:
            payload = dict(state)
            payload["is_admin"] = getattr(ws, "is_admin_flag", False)
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        room_state.remove_listener(chat_id, ws)


def create_app() -> FastAPI:
    app_ = FastAPI(title="AnonXMusic Room")

    @app_.get("/")
    async def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app_.get("/favicon.ico")
    async def favicon():
        return JSONResponse({}, status_code=204)

    @app_.get("/api/room/{chat_id}")
    async def room_info(chat_id: int):
        return JSONResponse(await build_state(chat_id))

    @app_.post("/api/control/{chat_id}")
    async def control(chat_id: int, action: str, user_id: int):
        from anony import anon, db
        from anony.helpers import is_admin

        if not await is_admin(chat_id, user_id):
            return JSONResponse({"ok": False, "error": "not_admin"}, status_code=403)
        if not await db.get_call(chat_id):
            return JSONResponse({"ok": False, "error": "not_playing"}, status_code=400)

        from anony.web.state import room_state
        clock = room_state.clock(chat_id)

        if action == "pause":
            await anon.pause(chat_id)
            clock.pause()
        elif action == "resume":
            await anon.resume(chat_id)
            clock.resume()
        elif action == "skip":
            await anon.play_next(chat_id)
        elif action == "stop":
            await anon.stop(chat_id)
        else:
            return JSONResponse({"ok": False, "error": "unknown_action"}, status_code=400)

        await broadcast(chat_id)
        return JSONResponse({"ok": True})

    @app_.websocket("/ws/{chat_id}/{user_id}")
    async def ws_room(websocket: WebSocket, chat_id: int, user_id: int = 0):
        from anony.helpers import is_admin
        from anony.web.state import room_state

        await websocket.accept()
        websocket.is_admin_flag = await is_admin(chat_id, user_id) if user_id else False
        room_state.add_listener(chat_id, websocket)
        try:
            first = await build_state(chat_id)
            first["is_admin"] = websocket.is_admin_flag
            await websocket.send_json(first)
            await broadcast(chat_id)  # update listener count for everyone
            while True:
                # Website doesn't push anything over the socket except a
                # periodic ping to keep the connection alive — all real
                # actions go through POST /api/control (simpler to gate
                # with is_admin there than inside a long-lived socket).
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug(f"ws_room[{chat_id}]: {e}")
        finally:
            room_state.remove_listener(chat_id, websocket)
            await broadcast(chat_id)

    app_.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app_

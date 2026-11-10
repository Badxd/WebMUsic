# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AloneXMusic

"""
alonex/web/server.py — the mini "room" webapp.

Read-mostly by design: AloneX's own queue/calls/db stay the single
source of truth. This layer only (a) reports that state live over a
websocket and (b) forwards a handful of admin-gated controls into the
exact same functions the /pause /resume /skip commands already call —
nothing here duplicates AloneX's playback logic.

Speed is intentionally NOT controllable from here — see
alonex/plugins/speed.py: it's a group-chat command only.
"""
import json
import logging
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("alonex.web")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _media_to_dict(media, chat_id: int) -> dict:
    from alonex.web.state import room_state
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
    from alonex import app
    from alonex.web.state import room_state

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
    from alonex import queue, db
    from alonex.web.state import room_state

    media = queue.get_current(chat_id)
    is_live = bool(await db.get_call(chat_id))
    return {
        "type":      "state",
        "chat_id":   chat_id,
        "chat_name": await _chat_title(chat_id),
        "active":    is_live and media is not None,
        "song":      _media_to_dict(media, chat_id) if (is_live and media) else None,
        "queue": [
            {"title": m.title, "duration": m.duration, "requested_by": m.user}
            for m in queue.get_queue(chat_id)
        ][:20],
        "listeners":      room_state.listener_count(chat_id),
        "listener_people": room_state.listener_people(chat_id)[:50],
        "chat_log":       room_state.chat_log.get(chat_id, [])[-30:],
    }


async def _send_to_room(chat_id: int, payload: dict, skip: "WebSocket" = None):
    from alonex.web.state import room_state
    dead = []
    for ws in list(room_state.listeners.get(chat_id, ())):
        if ws is skip:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        room_state.remove_listener(chat_id, ws)


async def broadcast(chat_id: int):
    """Call this after anything changes the room — play/pause/resume/
    skip/stop — so every open tab updates immediately. Each listener
    gets the same room state, PLUS their own is_admin flag (computed
    once at connect time — see ws_room below) so the website only
    shows transport controls to actual group admins, same gate the
    POST /api/control endpoint enforces."""
    from alonex.web.state import room_state
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


async def broadcast_system(chat_id: int, event: str, person: dict):
    """'X joined the room' / 'X left' — ephemeral, shown as a toast on
    every open tab, never written to any database."""
    await _send_to_room(chat_id, {"type": "system", "event": event, "person": person})


def create_app() -> FastAPI:
    app_ = FastAPI(title="AloneXMusic Room")

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
        from alonex import anon, db
        from alonex.helpers import is_admin

        if not await is_admin(chat_id, user_id):
            return JSONResponse({"ok": False, "error": "not_admin"}, status_code=403)
        if not await db.get_call(chat_id):
            return JSONResponse({"ok": False, "error": "not_playing"}, status_code=400)

        from alonex.web.state import room_state
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
        import time as _t
        from alonex.helpers import is_admin
        from alonex.web.state import room_state

        q = websocket.query_params
        person = {
            "user_id":    user_id,
            "name":       (q.get("name") or "Guest")[:40],
            "username":   q.get("username") or "",
            "photo_url":  q.get("photo") or "",
        }

        await websocket.accept()
        websocket.is_admin_flag = await is_admin(chat_id, user_id) if user_id else False
        websocket.person = person
        room_state.add_listener(chat_id, websocket)
        try:
            first = await build_state(chat_id)
            first["is_admin"] = websocket.is_admin_flag
            await websocket.send_json(first)
            await broadcast(chat_id)  # update listener count/people for everyone
            if user_id:
                await broadcast_system(chat_id, "joined", person)

            while True:
                raw = await websocket.receive_text()
                if raw == "ping":
                    continue  # client keep-alive, nothing to do
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                if msg.get("type") == "chat":
                    text = str(msg.get("text", "")).strip()[:300]
                    if not text or not user_id:
                        continue
                    chat_msg = {
                        "type": "chat", "person": person, "text": text, "ts": _t.time(),
                    }
                    room_state.add_chat(chat_id, chat_msg)
                    await _send_to_room(chat_id, chat_msg)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug(f"ws_room[{chat_id}]: {e}")
        finally:
            room_state.remove_listener(chat_id, websocket)
            await broadcast(chat_id)
            if user_id and not any(
                getattr(w, "person", {}).get("user_id") == user_id
                for w in room_state.listeners.get(chat_id, ())
            ):
                await broadcast_system(chat_id, "left", person)

    app_.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app_

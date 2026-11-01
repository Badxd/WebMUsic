# web/app.py

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager  # ✅ ADD

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.player import rooms_manager
from web.routes  import router
from web.websocket import _build_state

logger = logging.getLogger("WebApp")

_pyro_client = None


def set_pyro_client(client):
    global _pyro_client
    _pyro_client = client
    logger.info("Pyrogram client injected ✅")


# ✅ FIX 1: Lifespan add karo — CancelledError hatao
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # startup → shutdown cleanly


def create_webapp() -> FastAPI:
    app = FastAPI(lifespan=lifespan)  # ✅ lifespan pass karo
    app.include_router(router)

    @app.websocket("/ws/{chat_id}/{username}")
    async def ws_route(
        websocket: WebSocket,
        chat_id:   int,
        username:  str,
        user_id:   int = Query(default=0),
    ):
        await websocket.accept()

        if user_id in rooms_manager.blacklisted_users:
            await websocket.close(code=4003)
            return

        room   = rooms_manager.get_room(chat_id)
        ws_key = str(id(websocket))
        room.listeners.append(websocket)
        room.listener_info[ws_key] = {
            "username": username,
            "user_id":  user_id,
            "is_admin": rooms_manager.is_admin(user_id),
        }

        try:
            await websocket.send_json(_build_state(chat_id))
        except Exception:
            pass
        await _broadcast(chat_id)

        if room.current_song and _pyro_client:
            from BadMusic.modules.settings import announce_join_to_group
            asyncio.create_task(
                announce_join_to_group(
                    _pyro_client, chat_id, username,
                    room.current_song.get("title", "")
                )
            )

        # ✅ FIX 2: get_event_loop() → get_running_loop()
        loop = asyncio.get_running_loop()
        listen_start = loop.time()

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                mtype = msg.get("type", "")

                if mtype == "chat":
                    msg_text = msg.get("message", "")
                    # Handle /commands typed in webapp chat
                    if msg_text.startswith("/") and _pyro_client:
                        from BadMusic.modules.play import handle_chat_command
                        try:
                            result = await handle_chat_command(
                                _pyro_client, chat_id, user_id, username, msg_text
                            )
                            if result:
                                await _broadcast_system(chat_id, f"{username}: {msg_text}  →  {result}")
                        except Exception as e:
                            logger.error(f"chat_command error: {e}")
                        continue

                    await _broadcast_chat(
                        chat_id,
                        msg.get("username", username),
                        msg_text,
                        user_id,
                        msg_type="text",
                    )
                    await _broadcast_seen(chat_id, username, user_id)
                    continue

                if mtype == "typing":
                    await _broadcast_typing(chat_id, username, user_id, True)
                    continue

                if mtype == "stop_typing":
                    await _broadcast_typing(chat_id, username, user_id, False)
                    continue

                if mtype == "seen":
                    await _broadcast_seen(chat_id, username, user_id)
                    continue

                if mtype == "voice":
                    await _broadcast_chat(
                        chat_id,
                        msg.get("username", username),
                        msg.get("data", ""),
                        user_id,
                        msg_type="voice",
                        extra={"duration": msg.get("duration", 0)},
                    )
                    continue

                if mtype == "media":
                    await _broadcast_chat(
                        chat_id,
                        msg.get("username", username),
                        msg.get("url", ""),
                        user_id,
                        msg_type="media",
                        extra={
                            "mime":     msg.get("mime", ""),
                            "filename": msg.get("filename", "file"),
                            "size":     msg.get("size", 0),
                        },
                    )
                    continue

                if mtype in ("webrtc_offer", "webrtc_answer", "webrtc_ice", "call_join", "call_leave", "call_mute"):
                    msg["from_user_id"]  = user_id
                    msg["from_username"] = username
                    if mtype == "call_mute":
                        if not rooms_manager.is_admin(user_id):
                            continue
                    await _broadcast_webrtc(
                        chat_id, msg,
                        exclude_ws=None if mtype in ("call_join", "call_leave", "call_mute") else websocket
                    )
                    continue

                if not rooms_manager.is_admin(user_id):
                    continue

                # ✅ FIX 3: loop upar define ho chuka hai, dobara nahi banana
                if mtype == "play":
                    room.seek_time          = float(msg.get("seek_time", room.get_current_seek()))
                    room.last_update_time   = loop.time()
                    room._stream.is_playing = True
                    await _broadcast(chat_id)

                elif mtype == "pause":
                    if room.is_playing:
                        room.seek_time          = float(msg.get("seek_time", room.get_current_seek()))
                        room._stream.is_playing = False
                        room.last_update_time   = loop.time()
                        await _broadcast(chat_id)

                elif mtype == "seek":
                    room.seek_time        = float(msg.get("seek_time", 0))
                    room.last_update_time = loop.time()
                    await _broadcast(chat_id)

                elif mtype == "skip":
                    await room.skip_song()

                elif mtype == "stop":
                    await room.stop_session()

        except WebSocketDisconnect:
            pass
        finally:
            if websocket in room.listeners:
                room.listeners.remove(websocket)
            room.listener_info.pop(ws_key, None)
            if user_id:
                # ✅ FIX 4: loop already defined upar
                elapsed = int(loop.time() - listen_start)
                if elapsed > 5:
                    await rooms_manager.increment_user_stat(user_id, seconds_delta=elapsed)
            await _broadcast_system(chat_id, f"{username} left the room.")
            await _broadcast(chat_id)

    # ── File upload ────────────────────────────────────────
    @app.post("/upload_media")
    async def upload_media(
        file:     UploadFile = File(...),
        chat_id:  int        = Form(...),
        user_id:  int        = Form(0),
        username: str        = Form(""),
    ):
        MAX_SIZE = 10 * 1024 * 1024
        contents = await file.read()
        if len(contents) > MAX_SIZE:
            return JSONResponse({"ok": False, "error": "File too large (max 10MB)"}, status_code=413)

        safe_name = os.path.basename(file.filename or "file")
        save_path = os.path.join("static", "uploads", f"{int(time.time())}_{safe_name}")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(contents)

        url = f"/static/uploads/{os.path.basename(save_path)}"
        await _broadcast_chat(
            chat_id, username, url, user_id,
            msg_type="media",
            extra={"mime": file.content_type or "", "filename": safe_name, "size": len(contents)},
        )
        return JSONResponse({"ok": True, "url": url})

    # ── Static files ───────────────────────────────────────
    os.makedirs("static/downloads", exist_ok=True)
    os.makedirs("static/uploads",   exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/favicon.ico")
    async def favicon():
        p = "static/favicon.ico"
        return FileResponse(p) if os.path.exists(p) else JSONResponse({})

    @app.get("/")
    async def root():
        return FileResponse("static/index.html")

    rooms_manager.set_broadcast_callback(_broadcast)
    return app


# ── Broadcast helpers ──────────────────────────────────────

async def _broadcast(chat_id: int):
    room  = rooms_manager.get_room(chat_id)
    state = _build_state(chat_id)
    dead  = []
    for ws in list(room.listeners):
        try:
            await ws.send_json(state)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in room.listeners:
            room.listeners.remove(ws)
        room.listener_info.pop(str(id(ws)), None)


async def _broadcast_chat(
    chat_id: int, username: str, message: str,
    user_id: int = 0, msg_type: str = "text", extra: dict = None,
):
    room    = rooms_manager.get_room(chat_id)
    payload = {
        "type":     "chat",
        "sub_type": msg_type,
        "username": username,
        "user_id":  user_id,
        "message":  message[:500] if msg_type == "text" else message,
        "ts":       int(time.time()),
    }
    if extra:
        payload.update(extra)
    for ws in list(room.listeners):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


async def _broadcast_typing(chat_id: int, username: str, user_id: int, is_typing: bool):
    room    = rooms_manager.get_room(chat_id)
    payload = {"type": "typing", "username": username, "user_id": user_id, "is_typing": is_typing}
    for ws in list(room.listeners):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


async def _broadcast_seen(chat_id: int, username: str, user_id: int):
    room    = rooms_manager.get_room(chat_id)
    payload = {"type": "seen", "username": username, "user_id": user_id, "ts": int(time.time())}
    for ws in list(room.listeners):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


async def _broadcast_system(chat_id: int, text: str):
    room    = rooms_manager.get_room(chat_id)
    payload = {"type": "system", "message": text}
    for ws in list(room.listeners):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


async def _broadcast_webrtc(chat_id: int, payload: dict, exclude_ws=None):
    room = rooms_manager.get_room(chat_id)
    for ws in list(room.listeners):
        if ws is exclude_ws:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            pass
                        

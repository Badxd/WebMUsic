# 🎧 Mini Webapp Room

A small listen-together website added on top of AloneXMusic, in the
same spirit as Playeon's room link — short clean URLs, the real group
name on the join screen, and nothing duplicated: it reads AloneX's own
queue/call state live, it doesn't run a second playback system.

## What's new

- **`alonex/web/`** — the FastAPI app (`server.py`), the tiny per-chat
  clock that tracks live playback position (`state.py`), and the
  frontend (`static/`).
- **`alonex/plugins/speed.py`** — new `/speed <0.5–2.0>` command.
  Playback speed is **group-chat only, on purpose** — it changes the
  real Voice Chat stream (re-encoded via ffmpeg), so it needs the
  same admin gate every other transport command already uses. The
  website mirrors whatever speed is set but has no control for it.
- **`🎧 Open Room` button** — added to the now-playing card
  (`alonex/helpers/_inline.py`), linking to `{MINIAPP_LINK}?startapp=
  N<chat_id>` — just the chat_id, nothing else encoded. The page
  fetches the real song/queue/title live once it's open, so the link
  never goes stale.
- **Group name on join** — the join screen calls `app.get_chat()` and
  shows the actual group's name/title before you even join, like
  Playeon does.
- **Neon theme** — `alonex/web/static/css/style.css`: dark background,
  cyan → violet → magenta gradient, glow accents.
- **Clean page** — just the room: join screen → player (art, title,
  progress, listener count, Play/Pause/Skip for admins). No
  chat/profile/playlist tabs bolted on.

## 🙌 Chat / People / Profile tabs

The room is now a small tabbed app (Player / Chat / People / Profile),
styled after telegram-web-player's cleaner look — but these three new
tabs are **ephemeral on purpose**, not a new social/database feature:

- **Chat** — a live chat relayed over the same websocket everyone's
  already connected on. Nothing is saved: it's kept in memory per
  room (last 50 messages) and disappears once the room is empty.
  Only Telegram-identified users (opened via the bot, not a bare
  browser tab) can send messages.
- **People** — who's actually in the room right now, with their
  Telegram name/photo (from Telegram's own WebApp data — nothing
  stored server-side beyond "currently connected").
- **Profile** — your own name/photo (again, straight from Telegram,
  no account system) plus a simple "time in this room" counter.
- **Join/leave toasts** — "X joined 👋" / "X left" shown live to
  everyone else in the room.

**What this deliberately doesn't include:** a friends system, saved
playlists/favorites, persistent chat history, or user accounts — all
of that needs real per-user database storage and its own set of
endpoints, which is a separate, much bigger project from "make the
existing room richer." Happy to scope that out properly if you want
it next.

## Setup

In your `.env` (see `sample.env`):

```
WEBAPP_ENABLED=True
PORT=8000
MINIAPP_LINK=https://t.me/YourBot/room
```

Create the Mini App with @BotFather first (`/newapp`) pointing at
wherever you deploy this (Heroku, Render, your own server — anything
that can reach `PORT`), then put that Mini App's `t.me/...` link in
`MINIAPP_LINK`.

Leave `MINIAPP_LINK` empty and the bot runs exactly as before — the
`🎧 Open Room` button just won't be added, and the mini webapp server
still runs (harmless) unless you also set `WEBAPP_ENABLED=False`.

## Notes / limits

- `/speed` text (`play_speed_usage` etc.) currently only has an
  English fallback — it wasn't added to AloneX's other 12 locale
  files (`alonex/locales/*.json`), so non-English groups will see the
  English text for that one command until those are translated too.
- Changing speed restarts the current track in the Voice Chat from
  the same position (not frame-exact) — unavoidable since it's a live
  re-encode, not pre-processed audio.
- Regular (non-admin) listeners can open the room and listen to the
  live state, but can't control playback — same permission model as
  every other AloneX transport command.

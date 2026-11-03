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

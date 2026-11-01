# 🎵 Bad Music Bot

A fast, powerful Telegram music bot with a WebApp player.  
Play YouTube songs live in any group — listeners sync in real time via WebSocket.

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/your-username/BadMusic)

> Push this project to your own GitHub repo first, then update the
> `repository` field in `app.json` (and the link above) to point to
> it — Heroku's button reads `app.json` from that repo to build the
> deploy form automatically.

---

## 🟣 Deploy on Heroku

This repo ships ready for Heroku: `app.json`, `Procfile`, `runtime.txt`.

1. Push the project to a GitHub repo.
2. Click **Deploy to Heroku** (button above) or go to
   `https://heroku.com/deploy?template=<your-repo-url>`.
3. Fill in `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID` (the required
   ones — everything else, including `STRING_SESSION` for Voice Chat,
   is optional and can be added later from **Settings → Config Vars**).
4. Deploy. Once it's live, copy your app's URL
   (`https://your-app.herokuapp.com`) into the `WEBAPP_URL` config var
   and restart the dyno so the mini web player's links are correct.
5. `ffmpeg` is installed automatically via the ffmpeg buildpack in
   `app.json` — no extra setup needed.

**Notes for Heroku specifically:**
- It's a **web** dyno (`Procfile`) — the app binds to Heroku's `$PORT`
  automatically via `config.PORT`, so the free/eco dyno won't be
  killed for not binding.
- Heroku's filesystem is **ephemeral** — if `MONGO_URL` is left empty,
  the local `database.json` / downloaded songs are wiped on every
  restart/dyno-cycle. For anything you want to persist (admins,
  blacklist, favorites, the `/vcmusic` on/off switches, profiles),
  set `MONGO_URL` to a free MongoDB Atlas cluster.
- Eco/Basic dynos sleep after inactivity on some plans — fine for a
  hobby bot, but for a bot that must always be instantly responsive
  use at least a Basic dyno with no sleep, or a different host.

---

## ✨ Features

- 🎵 YouTube search & play via `/play`
- 📞 **Real Telegram Voice Chat streaming** (PyTgCalls) — the song plays
  in the group's actual VC through an assistant account, exactly like
  ShizuMusic, at the same time as the web room below
- 📋 Queue system — add multiple songs, auto-plays next (VC + web room
  always stay on the same track)
- 🌐 WebApp player — listeners join a live room and hear the same song in
  sync, now with a clean Apple-Music-style player design
- ❤️ Favorites — save songs, queue them from your profile
- 🔐 Admin system — authorize users to control playback
- 📊 Activity logger — `/start`, group add/remove, songs played, kicks all logged
- 🔇 Auto-delete commands — keeps group chat clean
- 🗃️ MongoDB support with local JSON fallback

### 🔊 Enabling real Voice Chat audio

1. Generate a `STRING_SESSION` for a normal Telegram **user** account
   (not the bot) with any Pyrogram string-session generator.
2. Add that account to your group and make sure it's allowed to join
   Voice Chats (admin is safest).
3. Put the string in `.env` as `STRING_SESSION=...` and set
   `py-tgcalls` / `ntgcalls` from `requirements.txt`.
4. Start a Voice Chat in the group, then `/play <song>` — the bot
   joins the VC automatically and streams the same file the web room
   is playing. `/pause`, `/resume`, `/skip`, `/stop` control both at once.

If `STRING_SESSION` is left empty, the bot runs exactly as before —
web-room-only, no crash, no VC.

### 🎚 Turning Voice Chat ON/OFF whenever you want

No restart, no `.env` edit needed — control it live with a command:

| Command | Who | What it does |
|---|---|---|
| `/vcmusic` | anyone | shows VC status (this group + global) |
| `/vcmusic on` | group admin | turns real VC streaming **ON** for this group |
| `/vcmusic off` | group admin | turns it **OFF** for this group — assistant leaves the VC immediately, web room keeps playing, zero extra load |
| `/vcmusic global on` | bot owner | turns VC **ON** bot-wide |
| `/vcmusic global off` | bot owner | turns VC **OFF** bot-wide instantly (kill-switch) |

Groups that switch VC off stay 100% web-room-only — the bot skips VC
entirely for them (checked in-memory, no extra DB/network cost), so
it never adds assistant/ffmpeg load to a group that doesn't want it.
The setting is saved (MongoDB or local `database.json`), so it
survives restarts.

---

## 📁 Project Structure

```
BadMusic/
├── main.py              ← Entry point
├── config.py            ← All env vars and constants
├── requirements.txt
├── .env                 ← Your secrets (never commit this)
│
├── core/
│   ├── player.py        ← MusicRoom + RoomsManager
│   ├── queue.py         ← Per-room queue logic
│   ├── stream.py        ← Playback state (seek/play/pause)
│   └── utils.py         ← Formatting helpers, deep-link encode
│
├── plugins/
│   ├── __init__.py      ← Registers all handlers
│   ├── _events.py       ← Bot added/removed from group logger
│   ├── start.py         ← /start /help (with image + logger)
│   ├── play.py          ← /play command + inline search
│   ├── skip.py          ← /skip
│   ├── stop.py          ← /stop /end /pause /resume
│   └── settings.py      ← /setting /fav /auth /ping /queue
│                           + watchdog + timer + kick logger
│
├── web/
│   ├── app.py           ← FastAPI factory + bot startup
│   ├── routes.py        ← REST API endpoints
│   └── websocket.py     ← WebSocket handler
│
├── database/
│   ├── mongo.py         ← MongoDB class (admins, stats, favorites)
│   └── models.py        ← TypedDict shapes
│
├── services/
│   ├── youtube.py       ← YouTube search
│   └── downloader.py    ← Audio download + cache
│
└── static/
    ├── index.html
    ├── css/style.css
    └── js/script.js
```

---

## ⚙️ Setup & Hosting

### 1. Clone / Upload files

```bash
cd ~
# Upload the BadMusic folder to your server via SCP or SFTP
```

### 2. Install dependencies

```bash
cd ~/BadMusic
pip install -r requirements.txt
```

### 3. Configure `.env`

Edit the `.env` file:

```env
BOT_TOKEN=YOUR_BOT_TOKEN_HERE          # From @BotFather
OWNER_ID=YOUR_TELEGRAM_USER_ID         # Your Telegram numeric ID
LOGGER_ID=YOUR_LOG_GROUP_OR_CHANNEL    # Group/channel ID for activity logs
WEBAPP_URL=https://your-domain.com     # Your server's public URL
MINIAPP_LINK=https://t.me/YourBot/app  # Telegram Mini App link
SUPPORT_CHAT=https://t.me/YourGroup   # Support group link
MONGO_DB_URI=mongodb+srv://...         # Optional, leave blank to use local JSON
DB_NAME=BadMusic
PORT=8000
```

> **How to get your OWNER_ID:** Message [@userinfobot](https://t.me/userinfobot) on Telegram.  
> **How to get LOGGER_ID:** Add [@getidsbot](https://t.me/getidsbot) to your log group.

### 4. Set up Telegram Mini App

1. Open [@BotFather](https://t.me/BotFather)
2. Send `/newapp` → choose your bot → fill in details
3. Set **Web App URL** to `https://your-domain.com`
4. Copy the mini app link → put it in `MINIAPP_LINK` in `.env`

### 5. Run the bot

**Foreground (for testing):**
```bash
cd ~/BadMusic
python3 -m main
```

**Background (production):**
```bash
cd ~/BadMusic
nohup python3 -m main > logs/bot.log 2>&1 &
echo "PID: $!"
```

**Stop it:**
```bash
pkill -f "python3 -m main"
```

**Check logs:**
```bash
tail -f ~/BadMusic/logs/bot.log
```

---

## 🤖 Bot Commands

| Command | Who | Description |
|---------|-----|-------------|
| `/start` | Everyone | Start the bot |
| `/help` | Everyone | Show help menu |
| `/play <song>` | Everyone | Search and play a song |
| `/skip` | Admin | Skip current song |
| `/pause` | Admin | Pause playback |
| `/resume` | Admin | Resume playback |
| `/stop` | Admin | Stop current song |
| `/end` | Admin | End session, clear all queues |
| `/queue` | Everyone | View current queue |
| `/fav` | Everyone | Save current song to favorites |
| `/ping` | Everyone | Check bot latency |
| `/setting` | Admin | Toggle join/queue announcements |
| `/auth` | Owner | Authorize a user as admin (reply) |
| `/unauth` | Owner | Remove admin (reply) |
| `/blacklist` | Admin | Block a user (reply) |
| `/clean` | Admin | Clear downloaded audio cache |

---

## 📊 Logger Events (sent to LOGGER_ID)

| Event | Trigger |
|-------|---------|
| 🚀 Bot Started | Someone sends `/start` in private |
| ➕ Bot Added to Group | Bot is added to any group |
| ➖ Bot Removed from Group | Bot is kicked/removed |
| 🎵 Song Played | Any `/play` command succeeds |
| 🚫 User Kicked/Banned | Admin kicks a user in any group |

---

## 🔧 Nginx Reverse Proxy (optional)

If you want `https://your-domain.com` to point to the bot:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
    }
}
```

Then use [Certbot](https://certbot.eff.org/) for HTTPS:
```bash
sudo certbot --nginx -d your-domain.com
```

---

## ❓ Common Issues

| Problem | Fix |
|---------|-----|
| `409 Conflict` | Two instances running. Run `pkill -f "python3 -m main"` then restart |
| `Message to be replied not found` | Already fixed — bot uses standalone messages |
| `sendPhoto 400 Bad Request` | Already fixed — uses permanent YouTube thumbnail URLs |
| Bot not responding | Check `logs/bot.log` for errors |
| Song not playing in WebApp | Make sure `WEBAPP_URL` and `MINIAPP_LINK` are set correctly |

---

## 📝 License

Built for personal/private use. Do not redistribute without permission.

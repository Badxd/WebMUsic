"""
database/mongo.py — MongoDB connection + all database operations
Single Database class used across the whole app.

FIX: All `if not self.db:` replaced with `if self.db is None:`
     Motor's AsyncIOMotorDatabase does NOT support bool() — was crashing.
"""
import json
import logging
import os
from typing import Dict, List, Optional, Set

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URL, DB_NAME

logger = logging.getLogger("Database")


class Database:
    def __init__(self):
        self.client = None
        self.db     = None   # AsyncIOMotorDatabase | None
        # In-memory fallback when no MongoDB
        self._admins:      Set[int] = set()
        self._blacklisted: Set[int] = set()
        # ── Voice Chat on/off switches ──────────────────────
        # Per-group opt-in/opt-out — groups that don't want real VC
        # streaming (and the extra load it adds) can switch it off,
        # and the bot simply stays web-room-only for them.
        self._vc_disabled_chats: Set[int] = set()
        # One global kill-switch (owner only) — instantly turns VC
        # off/on everywhere without touching the server .env.
        self._vc_global_enabled: bool = True
        self._local_path = "database.json"

    # ── Connection ─────────────────────────────────────────
    async def connect(self):
        if MONGO_URL:
            try:
                self.client = AsyncIOMotorClient(MONGO_URL)
                self.db     = self.client[DB_NAME]
                await self._load_settings()
                logger.info("MongoDB connected ✅")
                return
            except Exception as e:
                logger.warning(f"MongoDB failed ({e}), using local JSON fallback")
        self.db = None
        self._load_local()

    async def _load_settings(self):
        doc = await self.db.settings.find_one({"id": "global"})
        if doc:
            self._admins            = set(doc.get("admins",      []))
            self._blacklisted       = set(doc.get("blacklisted", []))
            self._vc_disabled_chats = set(doc.get("vc_disabled_chats", []))
            self._vc_global_enabled = doc.get("vc_global_enabled", True)

    def _load_local(self):
        if os.path.exists(self._local_path):
            try:
                with open(self._local_path) as f:
                    d = json.load(f)
                    self._admins            = set(d.get("admins",      []))
                    self._blacklisted       = set(d.get("blacklisted", []))
                    self._vc_disabled_chats = set(d.get("vc_disabled_chats", []))
                    self._vc_global_enabled = d.get("vc_global_enabled", True)
            except Exception:
                pass

    async def _save(self):
        data = {
            "admins":             list(self._admins),
            "blacklisted":        list(self._blacklisted),
            "vc_disabled_chats":  list(self._vc_disabled_chats),
            "vc_global_enabled":  self._vc_global_enabled,
        }
        if self.db is not None:           # ✅ FIXED
            await self.db.settings.update_one(
                {"id": "global"}, {"$set": data}, upsert=True)
        else:
            try:
                with open(self._local_path, "w") as f:
                    json.dump(data, f)
            except Exception:
                pass

    # ── Admins ─────────────────────────────────────────────
    def is_admin(self, user_id: int, owner_id: int = 0) -> bool:
        return user_id == owner_id or user_id in self._admins

    async def add_admin(self, user_id: int):
        self._admins.add(user_id)
        await self._save()

    async def remove_admin(self, user_id: int):
        self._admins.discard(user_id)
        await self._save()

    # ── Blacklist ──────────────────────────────────────────
    def is_blacklisted(self, user_id: int) -> bool:
        return user_id in self._blacklisted

    async def blacklist(self, user_id: int):
        self._blacklisted.add(user_id)
        self._admins.discard(user_id)
        await self._save()

    async def unblacklist(self, user_id: int):
        self._blacklisted.discard(user_id)
        await self._save()

    # ── Voice Chat on/off (per group + global) ──────────────
    def is_vc_enabled(self, chat_id: int) -> bool:
        """Fast, in-memory, no I/O — safe to call on every song."""
        if not self._vc_global_enabled:
            return False
        return chat_id not in self._vc_disabled_chats

    async def set_vc_for_chat(self, chat_id: int, enabled: bool):
        if enabled:
            self._vc_disabled_chats.discard(chat_id)
        else:
            self._vc_disabled_chats.add(chat_id)
        await self._save()

    async def set_vc_global(self, enabled: bool):
        self._vc_global_enabled = enabled
        await self._save()

    # ── User Stats ─────────────────────────────────────────
    async def increment_stat(self, user_id: int, songs: int = 0, seconds: int = 0):
        if self.db is None:               # ✅ FIXED
            return
        try:
            upd = {}
            if songs:   upd["songs"]   = songs
            if seconds: upd["seconds"] = seconds
            if upd:
                await self.db.user_stats.update_one(
                    {"user_id": user_id}, {"$inc": upd}, upsert=True)
        except Exception as e:
            logger.error(f"increment_stat: {e}")

    async def get_stats(self, user_id: int) -> Dict:
        if self.db is None:               # ✅ FIXED
            return {"songs": 0, "seconds": 0}
        try:
            doc = await self.db.user_stats.find_one({"user_id": user_id})
            if doc:
                return {"songs": doc.get("songs", 0), "seconds": doc.get("seconds", 0)}
        except Exception:
            pass
        return {"songs": 0, "seconds": 0}

    # ── Favorites ──────────────────────────────────────────
    async def get_favorites(self, user_id: int) -> List[Dict]:
        if self.db is None:
            return []
        try:
            doc = await self.db.favorites.find_one({"user_id": user_id})
            if not doc:
                return []
            doc.pop("_id", None)
            return doc.get("songs", [])
        except Exception as e:
            logger.error(f"get_favorites: {e}")
            return []

    async def add_favorite(self, user_id: int, song: Dict) -> bool:
        if self.db is None:               # ✅ FIXED
            return False
        try:
            doc   = await self.db.favorites.find_one({"user_id": user_id})
            songs = doc.get("songs", []) if doc else []
            songs = [s for s in songs if s.get("link") != song.get("link")]
            songs.insert(0, song)
            songs = songs[:50]
            await self.db.favorites.update_one(
                {"user_id": user_id}, {"$set": {"songs": songs}}, upsert=True)
            return True
        except Exception as e:
            logger.error(f"add_favorite: {e}")
            return False

    async def remove_favorite(self, user_id: int, link: str) -> bool:
        if self.db is None:               # ✅ FIXED
            return False
        try:
            doc   = await self.db.favorites.find_one({"user_id": user_id})
            songs = doc.get("songs", []) if doc else []
            songs = [s for s in songs if s.get("link") != link]
            await self.db.favorites.update_one(
                {"user_id": user_id}, {"$set": {"songs": songs}}, upsert=True)
            return True
        except Exception as e:
            logger.error(f"remove_favorite: {e}")
            return False

    async def get_lang(self, chat_id: int) -> str:
        if self.db is None:               # ✅ FIXED
            return "en"
        try:
            doc = await self.db.lang.find_one({"chat_id": chat_id})
            return doc.get("lang", "en") if doc else "en"
        except Exception:
            return "en"

    async def set_lang(self, chat_id: int, lang: str):
        if self.db is None:               # ✅ FIXED
            return
        try:
            await self.db.lang.update_one(
                {"chat_id": chat_id}, {"$set": {"lang": lang}}, upsert=True)
        except Exception as e:
            logger.error(f"set_lang: {e}")

    async def get_profile(self, user_id: int) -> Dict:
        """Full profile: stats + streak + badges + listening history + bio."""
        if self.db is None:
            return self._empty_profile(user_id)
        try:
            doc = await self.db.profiles.find_one({"user_id": user_id})
            if not doc:
                return self._empty_profile(user_id)
            # ✅ FIX: Remove MongoDB ObjectId — not JSON serializable
            doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"get_profile: {e}")
            return self._empty_profile(user_id)

    def _empty_profile(self, user_id: int) -> Dict:
        return {
            "user_id": user_id,
            "bio": "",
            "theme_color": "#007aff",
            "streak": 0,
            "last_listen_date": "",
            "badges": [],
            "top_artists": [],
            "most_played": [],
            "weekly_hours": [0,0,0,0,0,0,0],
            "peak_hour": 0,
            "mood": {"bass_uses":0,"speed_uses":0,"night_listens":0,"songs_requested":0},
            "friends": [],
            "total_songs": 0,
            "total_seconds": 0,
            "rooms_joined": 0,
            "autoplay": False,
            "autoplay_query": "",
        }

    async def update_profile(self, user_id: int, update: Dict) -> bool:
        if self.db is None:
            return False
        try:
            await self.db.profiles.update_one(
                {"user_id": user_id}, {"$set": update}, upsert=True)
            return True
        except Exception as e:
            logger.error(f"update_profile: {e}")
            return False

    async def log_listen_session(self, user_id: int, song_title: str, artist: str,
                                  duration_sec: int, hour: int, bass_level: str,
                                  speed: float, chat_id: int) -> None:
        """Update streak, weekly chart, mood, top artists, most played."""
        if self.db is None:
            return
        import datetime
        today = datetime.date.today().isoformat()
        try:
            doc = await self.db.profiles.find_one({"user_id": user_id}) or {}
            # Streak
            last = doc.get("last_listen_date", "")
            streak = doc.get("streak", 0)
            if last == today:
                pass
            elif last == (datetime.date.today() - datetime.timedelta(days=1)).isoformat():
                streak += 1
            else:
                streak = 1

            # Weekly hours (0=Mon..6=Sun)
            weekly = doc.get("weekly_hours", [0]*7)
            day_idx = datetime.date.today().weekday()
            weekly[day_idx] = round(weekly[day_idx] + duration_sec/3600, 2)

            # Mood
            mood = doc.get("mood", {"bass_uses":0,"speed_uses":0,"night_listens":0,"songs_requested":0})
            if bass_level not in ("off",""):
                mood["bass_uses"] = mood.get("bass_uses",0) + 1
            if speed != 1.0:
                mood["speed_uses"] = mood.get("speed_uses",0) + 1
            if 0 <= hour < 5 or hour >= 23:
                mood["night_listens"] = mood.get("night_listens",0) + 1
            mood["songs_requested"] = mood.get("songs_requested",0) + 1

            # Top artists
            top_artists = doc.get("top_artists", [])
            found = next((a for a in top_artists if a["name"]==artist), None)
            if found:
                found["count"] = found.get("count",0)+1
            else:
                top_artists.append({"name": artist, "count": 1})
            top_artists = sorted(top_artists, key=lambda x: x["count"], reverse=True)[:10]

            # Most played songs
            most_played = doc.get("most_played", [])
            fsong = next((s for s in most_played if s["title"]==song_title), None)
            if fsong:
                fsong["count"] = fsong.get("count",0)+1
            else:
                most_played.append({"title": song_title, "count": 1})
            most_played = sorted(most_played, key=lambda x: x["count"], reverse=True)[:10]

            # Badges
            badges = set(doc.get("badges", []))
            if mood["night_listens"] >= 3:   badges.add("night_owl")
            if mood["bass_uses"] >= 10:      badges.add("bass_head")
            if mood["speed_uses"] >= 5:      badges.add("speed_runner")
            total_s = doc.get("total_songs",0) + 1
            if total_s >= 100:               badges.add("century")
            if total_s >= 1:                 badges.add("first_song")

            update = {
                "last_listen_date": today,
                "streak": streak,
                "weekly_hours": weekly,
                "peak_hour": hour,
                "mood": mood,
                "top_artists": top_artists,
                "most_played": most_played,
                "badges": list(badges),
                "total_songs": total_s,
                "total_seconds": doc.get("total_seconds",0) + duration_sec,
                "rooms_joined": doc.get("rooms_joined",0) + (1 if not doc else 0),
            }
            await self.db.profiles.update_one(
                {"user_id": user_id}, {"$set": update}, upsert=True)
        except Exception as e:
            logger.error(f"log_listen_session: {e}")

    # ── Friends / Social ───────────────────────────────────
    async def add_friend(self, user_id: int, friend_id: int, friend_name: str) -> bool:
        if self.db is None:
            return False
        try:
            await self.db.profiles.update_one(
                {"user_id": user_id},
                {"$addToSet": {"friends": {"id": friend_id, "name": friend_name}}},
                upsert=True)
            return True
        except Exception as e:
            logger.error(f"add_friend: {e}")
            return False

    async def remove_friend(self, user_id: int, friend_id: int) -> bool:
        if self.db is None:
            return False
        try:
            await self.db.profiles.update_one(
                {"user_id": user_id},
                {"$pull": {"friends": {"id": friend_id}}})
            return True
        except Exception as e:
            logger.error(f"remove_friend: {e}")
            return False

    async def get_friends(self, user_id: int) -> List[Dict]:
        if self.db is None:
            return []
        try:
            doc = await self.db.profiles.find_one({"user_id": user_id})
            if not doc:
                return []
            doc.pop("_id", None)
            return doc.get("friends", [])
        except Exception:
            return []

    # ── Autoplay setting ───────────────────────────────────
    async def get_autoplay(self, chat_id: int) -> Dict:
        if self.db is None:
            return {"enabled": False, "query": ""}
        try:
            doc = await self.db.autoplay.find_one({"chat_id": chat_id})
            if doc:
                return {"enabled": doc.get("enabled", False), "query": doc.get("query", "")}
        except Exception:
            pass
        return {"enabled": False, "query": ""}

    async def set_autoplay(self, chat_id: int, enabled: bool, query: str = "") -> bool:
        if self.db is None:
            return False
        try:
            await self.db.autoplay.update_one(
                {"chat_id": chat_id},
                {"$set": {"enabled": enabled, "query": query}},
                upsert=True)
            return True
        except Exception as e:
            logger.error(f"set_autoplay: {e}")
            return False

    # ── Room history ───────────────────────────────────────
    async def log_room_visit(self, user_id: int, chat_id: int, chat_name: str) -> None:
        if self.db is None:
            return
        import datetime
        try:
            await self.db.profiles.update_one(
                {"user_id": user_id},
                {"$push": {"room_history": {
                    "$each":  [{"chat_id": chat_id, "name": chat_name, "ts": datetime.datetime.utcnow().isoformat()}],
                    "$slice": -20,
                }}},
                upsert=True)
        except Exception as e:
            logger.error(f"log_room_visit: {e}")


# Single global instance used across entire app
db = Database()

# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AloneXMusic


import os
import re
import yt_dlp
import random
import asyncio
import aiohttp
from pathlib import Path

from py_yt import Playlist, VideosSearch

from alonex import config, logger
from alonex.helpers import Track, utils


class DummyLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass

class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "alonex/cookies"
        self.warned = False
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )

    def get_cookies(self):
        if not self.checked:
            for file in os.listdir(self.cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        async with aiohttp.ClientSession() as session:
            for url in urls:
                name = url.split("/")[-1]
                link = "https://batbin.me/raw/" + name
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(f"{self.cookie_dir}/{name}.txt", "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        return bool(re.match(self.iregex, url))

    # ── Search: Cookies/API toggle ───────────────────────────
    # config.USE_COOKIES True  -> cookies (yt-dlp) first, API fallback
    # config.USE_COOKIES False -> straight to API, cookies skipped
    # Either way, VideosSearch (py_yt) below stays as the final
    # fallback so a search never comes back completely empty just
    # because cookies/API aren't configured yet.

    def _blocking_cookie_search(self, query: str, cookie: str | None) -> dict | None:
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "geo_bypass": True, "nocheckcertificate": True,
            "logger": DummyLogger(), "socket_timeout": 15,
        }
        if cookie:
            opts["cookiefile"] = cookie
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            entries = (info or {}).get("entries") or []
            if not entries or not entries[0]:
                return None
            e = entries[0]
            if not e.get("id"):
                return None
            return {
                "id": e.get("id"),
                "channel": e.get("channel") or e.get("uploader") or "",
                "duration_sec": int(e.get("duration") or 0),
                "title": e.get("title", "Unknown"),
                "thumbnail": e.get("thumbnail") or f"https://img.youtube.com/vi/{e.get('id')}/hqdefault.jpg",
                "url": f"https://www.youtube.com/watch?v={e.get('id')}",
                "view_count": str(e.get("view_count") or ""),
            }

    async def _search_via_cookies(self, query: str) -> dict | None:
        cookie = self.get_cookies()
        try:
            return await asyncio.to_thread(self._blocking_cookie_search, query, cookie)
        except Exception as e:
            logger.warning(f"[cookies] search failed for '{query}': {e}")
            return None

    async def _search_via_api(self, query: str) -> dict | None:
        """GET {API_URL}/search?query=<q>&api_key=<key> — same
        API_URL/API_KEY as the downloader. Adjust field names below
        if your API's response shape differs."""
        if not (config.API_URL and config.API_KEY):
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{config.API_URL}/search",
                    params={"query": query, "api_key": config.API_KEY},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[api] search failed: HTTP {resp.status}")
                        return None
                    data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"[api] search error for '{query}': {e}")
            return None

        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            return None

        vid = data.get("id") or data.get("videoId") or ""
        url = data.get("url") or data.get("link") or (f"{self.base}{vid}" if vid else None)
        title = data.get("title")
        if not url or not title:
            return None
        return {
            "id": vid,
            "channel": data.get("channel") or "",
            "duration_sec": int(data.get("duration_sec") or data.get("seconds") or 0),
            "title": title,
            "thumbnail": data.get("thumbnail") or data.get("thumb")
                         or (f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else ""),
            "url": url,
            "view_count": str(data.get("view_count") or ""),
        }

    async def _search_resolved(self, query: str) -> dict | None:
        if config.USE_COOKIES:
            got = await self._search_via_cookies(query)
            if got:
                return got
            logger.info(f"[search] cookies failed, trying API for '{query}'")
            return await self._search_via_api(query)
        return await self._search_via_api(query)

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        resolved = await self._search_resolved(query)
        if resolved:
            dur_sec = resolved["duration_sec"]
            m, s = divmod(dur_sec, 60)
            h, m = divmod(m, 60)
            duration_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            return Track(
                id=resolved["id"],
                channel_name=resolved["channel"],
                duration=duration_str,
                duration_sec=dur_sec,
                message_id=m_id,
                title=resolved["title"][:25],
                thumbnail=resolved["thumbnail"],
                url=resolved["url"],
                view_count=resolved["view_count"],
                video=video,
            )

        try:
            _search = VideosSearch(query, limit=1, with_live=False)
            results = await _search.next()
        except Exception:
            return None
        if results and results["result"]:
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception:
            pass
        return tracks

    # ── Download: same Cookies/API toggle as search ─────────
    # config.USE_COOKIES True  -> cookies (yt-dlp) first, API fallback
    # config.USE_COOKIES False -> straight to API, cookies NEVER touched
    #   (previously this method always called get_cookies() no matter
    #   what, which is why "Cookies are missing" kept showing up even
    #   with USE_COOKIES=False — and why disabling it didn't actually
    #   switch anything to the API, since download() never tried the
    #   API at all before now).
    # Either way, a final bare yt-dlp attempt (no cookies) is the last
    # resort, so a download never fails outright just because cookies/
    # API aren't configured.

    async def _download_via_ytdlp(self, video_id: str, video: bool, use_cookies: bool) -> str | None:
        url = self.base + video_id
        ext = "mp4" if video else "webm"
        filename = f"downloads/{video_id}.{ext}"

        cookie = self.get_cookies() if use_cookies else None
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "logger": DummyLogger(),
            "nocheckcertificate": True,
            "remote_components": ["ejs:github"],
        }
        if cookie:
            base_opts["cookiefile"] = cookie

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[ext=webm][acodec=opus]",
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    return None
                except Exception as ex:
                    logger.warning("Download failed: %s", ex)
                    return None
            return filename

        return await asyncio.to_thread(_download)

    async def _download_via_api(self, video_id: str, video: bool = False) -> str | None:
        """GET {API_URL}/download?url=<id>&type=audio|video&api_key=<key>
        — same API the search toggle uses."""
        if not (config.API_URL and config.API_KEY):
            return None
        ext = "mp4" if video else "webm"
        filename = f"downloads/{video_id}.{ext}"
        tmp = filename + ".part"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{config.API_URL}/download",
                    params={"url": video_id, "type": "video" if video else "audio", "api_key": config.API_KEY},
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[api] download failed: HTTP {resp.status}")
                        return None
                    data = await resp.read()
        except Exception as e:
            logger.warning(f"[api] download error for {video_id}: {e}")
            return None

        if len(data) < 4096 or data[:1] in (b"{", b"<", b"["):
            logger.warning("[api] no media returned (check API_URL / API_KEY)")
            return None

        os.makedirs("downloads", exist_ok=True)
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, filename)
            return filename
        except OSError as e:
            logger.warning(f"[api] couldn't save download: {e}")
            return None

    async def download(self, video_id: str, video: bool = False) -> str | None:
        ext = "mp4" if video else "webm"
        filename = f"downloads/{video_id}.{ext}"
        if Path(filename).exists():
            return filename

        if config.USE_COOKIES:
            got = await self._download_via_ytdlp(video_id, video, use_cookies=True)
            if got:
                return got
            logger.info(f"[download] cookies failed, trying API for {video_id}")
            return await self._download_via_api(video_id, video)

        got = await self._download_via_api(video_id, video)
        if got:
            return got
        logger.info(f"[download] API not used/failed, trying plain yt-dlp for {video_id}")
        return await self._download_via_ytdlp(video_id, video, use_cookies=False)

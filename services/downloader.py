"""
services/downloader.py — Audio download + utilities + auto-cleanup

Download flow (same system as ShizuMusic):
  1. If API_URL + API_KEY are set → single request to
     {API_URL}/download?url=<id>&type=audio&api_key=<API_KEY>
     (this is exactly what was returning 401 before — the old code
     never sent an api_key at all, because no API_KEY config existed)
  2. If that's not configured, or it fails → plain yt-dlp, so the bot
     still works even with nothing set up.
  3. Nothing is hard-coded: set your own API_URL / API_KEY via env.
"""
import asyncio
import logging
import os
import re
import sys
import time
from typing import Optional

import aiofiles
import aiohttp

from config import (
    API_KEY,
    API_URL,
    API_URL_PASTEBIN,
    DOWNLOAD_DIR,
    FALLBACK_API_URL,
)

logger = logging.getLogger("Downloader")

_api_url: Optional[str] = None


async def _get_api_url() -> str:
    """Resolve which download-API base URL to use.
    Priority: your own API_URL (env) → pastebin-discovered fallback.
    """
    if API_URL:
        return API_URL

    global _api_url
    if _api_url:
        return _api_url
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(API_URL_PASTEBIN, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    url = (await r.text()).strip()
                    _api_url = url if url.startswith("http") else FALLBACK_API_URL
                    return _api_url
    except Exception as e:
        logger.warning(f"api_url fallback: {e}")
    _api_url = FALLBACK_API_URL
    return _api_url


def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    for pattern in [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"shorts\/([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def time_to_seconds(time_str: str) -> int:
    if not time_str or time_str in ("Unknown", "0:00", ""):
        return 0
    try:
        parts = list(map(int, str(time_str).strip().split(":")))
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        pass
    return 0


def get_thumbnail_url(video_id: str) -> str:
    """Permanent YouTube thumbnail URL — never expires."""
    return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"


def _cached(video_id: str) -> Optional[str]:
    path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        return f"/static/downloads/{video_id}.mp3"
    return None


async def _download_via_api(video_id: str) -> Optional[str]:
    """Single request: {API_URL}/download?url=<id>&type=audio&api_key=<KEY>
    — same system ShizuMusic uses. Returns None (never raises) so the
    caller can fall back to yt-dlp."""
    api_url = await _get_api_url()
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    tmp = file_path + ".part"
    try:
        params = {"url": video_id, "type": "audio"}
        if API_KEY:
            params["api_key"] = API_KEY

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{api_url}/download",
                params=params,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"[api] download failed: HTTP {resp.status} "
                        f"(check API_URL / API_KEY — set them in your env)"
                    )
                    return None
                async with aiofiles.open(tmp, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        await f.write(chunk)

        size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        bad = size < 4096
        if not bad:
            with open(tmp, "rb") as fh:
                bad = fh.read(1) in (b"{", b"<", b"[")  # looks like a JSON/HTML error body
        if bad:
            logger.warning("[api] no media returned (check API_URL / API_KEY)")
            _safe_remove(tmp)
            return None

        os.replace(tmp, file_path)
        logger.info(f"[api] downloaded {video_id} ({size // 1024} KB)")
        return f"/static/downloads/{video_id}.mp3"

    except asyncio.TimeoutError:
        logger.warning(f"[api] timeout for {video_id}")
    except Exception as e:
        logger.error(f"[api] download error: {e}")
    _safe_remove(tmp)
    return None


async def _download_via_ytdlp(video_id: str) -> Optional[str]:
    """Fallback: plain yt-dlp, no API needed at all."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    out_tmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--quiet", "--no-warnings", "--no-playlist", "--geo-bypass",
        "--no-overwrites", "--no-check-certificates",
        "-f", "bestaudio/best",
        "-x", "--audio-format", "mp3",
        "-o", out_tmpl,
        "--", f"https://www.youtube.com/watch?v={video_id}",
    ]
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(proc.communicate(), timeout=180)
        if proc.returncode != 0:
            tail = (err or b"").decode(errors="ignore").strip().splitlines()[-1:] or [""]
            logger.warning(f"[yt-dlp] failed for {video_id} (exit {proc.returncode}): {tail[0]}")
            return None
        found = _cached(video_id)
        if found:
            logger.info(f"[yt-dlp] downloaded {video_id}")
        return found
    except asyncio.TimeoutError:
        logger.warning(f"[yt-dlp] timed out for {video_id}")
        if proc and proc.returncode is None:
            proc.kill()
        return None
    except Exception as e:
        logger.error(f"[yt-dlp] error: {e}")
        return None


def _safe_remove(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


async def download_song(link: str) -> Optional[str]:
    """
    Download audio for a YouTube link to local disk.
    Returns /static/downloads/{id}.mp3 path on success, None on failure.
    Uses cached file if already downloaded. Tries the API first (if
    configured), then falls back to plain yt-dlp automatically.
    """
    video_id = extract_video_id(link)
    if not video_id:
        logger.error(f"download_song: invalid link={link}")
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    cached = _cached(video_id)
    if cached:
        return cached

    api_set = bool(API_KEY)  # API_URL falls back to pastebin-discovery even if unset
    if api_set:
        got = await _download_via_api(video_id)
        if got:
            return got
        logger.info(f"[dl] API failed, trying yt-dlp for {video_id}")

    return await _download_via_ytdlp(video_id)


# ─────────────────────────────────────────────────────────
#  AUTO-CLEANUP — delete song file after it finishes playing
# ─────────────────────────────────────────────────────────

def delete_song_file(video_id: str) -> bool:
    """
    Delete downloaded mp3 for a given video_id.
    Called after song ends / is skipped.
    """
    if not video_id:
        return False
    path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"🗑 Cleaned: {video_id}.mp3")
            return True
    except Exception as e:
        logger.warning(f"cleanup failed {video_id}: {e}")
    return False


async def cleanup_old_files(max_age_seconds: int = 3600) -> int:
    """
    Delete all mp3 files older than max_age_seconds (default 1 hour).
    Called periodically by watchdog.
    Returns count of deleted files.
    """
    deleted = 0
    try:
        if not os.path.exists(DOWNLOAD_DIR):
            return 0
        now = time.time()
        for fname in os.listdir(DOWNLOAD_DIR):
            if not fname.endswith(".mp3"):
                continue
            fpath = os.path.join(DOWNLOAD_DIR, fname)
            try:
                age = now - os.path.getmtime(fpath)
                if age > max_age_seconds:
                    os.remove(fpath)
                    deleted += 1
                    logger.info(f"🗑 Auto-cleaned: {fname} (age={int(age)}s)")
            except Exception as e:
                logger.warning(f"cleanup {fname}: {e}")
    except Exception as e:
        logger.error(f"cleanup_old_files: {e}")
    return deleted


async def get_disk_usage_mb() -> float:
    """Return DOWNLOAD_DIR size in MB."""
    total = 0
    try:
        for fname in os.listdir(DOWNLOAD_DIR):
            fpath = os.path.join(DOWNLOAD_DIR, fname)
            total += os.path.getsize(fpath)
    except Exception:
        pass
    return total / (1024 * 1024)

"""
services/downloader.py — Audio download + utilities + auto-cleanup
"""
import asyncio
import logging
import os
import re
import time
from typing import Optional

import aiofiles
import aiohttp

from config import DOWNLOAD_DIR, FALLBACK_API_URL, API_URL_PASTEBIN

logger = logging.getLogger("Downloader")

_api_url: Optional[str] = None


async def _get_api_url() -> str:
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


async def download_song(link: str) -> Optional[str]:
    """
    Download audio for a YouTube link to local disk.
    Returns /static/downloads/{id}.mp3 path on success, None on failure.
    Uses cached file if already downloaded.
    """
    api_url  = await _get_api_url()
    video_id = extract_video_id(link)
    if not video_id:
        logger.error(f"download_song: invalid link={link}")
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")

    # Return cached file if valid
    if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
        return f"/static/downloads/{video_id}.mp3"

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: get download token
            async with session.get(
                f"{api_url}/download",
                params={"url": video_id, "type": "audio"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"download token failed: {resp.status}")
                    return None
                data = await resp.json()

            token = data.get("download_token")
            if not token:
                logger.error("no download_token in response")
                return None

            # Step 2: stream to disk
            async with session.get(
                f"{api_url}/stream/{video_id}?type=audio",
                headers={"X-Download-Token": token},
                timeout=aiohttp.ClientTimeout(total=300),
            ) as stream:
                if stream.status != 200:
                    logger.error(f"stream failed: {stream.status}")
                    return None
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in stream.content.iter_chunked(16384):
                        await f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
            return f"/static/downloads/{video_id}.mp3"

        logger.error("downloaded file empty")
        if os.path.exists(file_path):
            os.remove(file_path)
        return None

    except asyncio.TimeoutError:
        logger.error(f"timeout for {video_id}")
    except Exception as e:
        logger.error(f"download_song: {e}")

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
    return None


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
    

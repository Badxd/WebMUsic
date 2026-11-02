# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll
# Original logic from thumbnails_best_.py — adapted for BadMusic

import asyncio
import os
import re
import random
import aiofiles
import aiohttp

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import config

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

NEON_COLORS = [
    (0, 255, 255),
    (255, 0, 255),
    (0, 255, 128),
    (255, 255, 0),
    (255, 105, 180),
]

_ASSETS  = os.path.join(os.path.dirname(__file__), "..", "assets")
_F_TITLE = os.path.join(_ASSETS, "fmt.ttf")
_F_META  = os.path.join(_ASSETS, "font.ttf")
_F_TAG   = os.path.join(_ASSETS, "font2.ttf")


def trim_to_width(text, font, max_w):
    ellipsis = "..."
    try:
        if font.getlength(text) <= max_w:
            return text
        for i in range(len(text) - 1, 0, -1):
            if font.getlength(text[:i] + ellipsis) <= max_w:
                return text[:i] + ellipsis
    except AttributeError:
        return text[:max_w // 10] + "..." if len(text) > max_w // 10 else text
    return ellipsis


def _blocking_lookup(videoid: str):
    """yt-dlp metadata lookup for ONE known video id — used only when the
    caller didn't already have the title/thumbnail (see get_thumb below).
    This replaces the old `youtubesearchpython` call, which is why the
    card used to fall back to 'Unknown Title' / the generic placeholder:
    that library was removed (it was broken — see the 401/`proxies`
    fixes) but this file was still trying to import it, so every lookup
    here silently failed and hit the `except` branch."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 15}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={videoid}", download=False)
    return info or {}


async def get_thumb(
    videoid: str,
    player_username: str = None,
    title: str = None,
    thumbnail_url: str = None,
    duration: str = None,
    views: str = None,
) -> str:
    """
    Build the neon 'now playing' card.
    Pass title/thumbnail_url/duration/views when the caller already has
    them (play.py does — from the same search result that found this
    song) so we never need a second network lookup at all. Only falls
    back to a fresh yt-dlp lookup if none of that was given.
    """
    player_username = player_username or "BadMusicBot"

    cache_path = os.path.join(CACHE_DIR, f"{videoid}_v5.png")
    if os.path.exists(cache_path):
        return cache_path

    if title and thumbnail_url:
        title = re.sub(r"\W+", " ", title).title()
        thumbnail = thumbnail_url
        duration_val = duration
        views_val = views or "Unknown Views"
    else:
        try:
            data = await asyncio.to_thread(_blocking_lookup, videoid)
            title = re.sub(r"\W+", " ", data.get("title", "Unknown Title")).title()
            thumbnail = data.get("thumbnail") or f"https://img.youtube.com/vi/{videoid}/hqdefault.jpg"
            duration_val = data.get("duration")  # seconds (int) here, formatted below
            if isinstance(duration_val, (int, float)):
                m, s = divmod(int(duration_val), 60)
                h, m = divmod(m, 60)
                duration_val = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            views_val = str(data.get("view_count") or "Unknown Views")
        except Exception as e:
            title, thumbnail, duration_val, views_val = "Unknown Title", config.YOUTUBE_IMG_URL, None, "Unknown Views"
    duration = duration_val
    views = views_val

    is_live       = not duration or str(duration).lower() in {"live", "live now", ""}
    duration_text = "Live" if is_live else duration or "Unknown"

    thumb_path = os.path.join(CACHE_DIR, f"thumb_{videoid}.png")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
                else:
                    return config.YOUTUBE_IMG_URL
    except Exception:
        return config.YOUTUBE_IMG_URL

    base    = Image.open(thumb_path).resize((1280, 720)).convert("RGBA")
    blur_bg = ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(20))).enhance(0.4)
    draw    = ImageDraw.Draw(blur_bg)
    w, h    = blur_bg.size

    rect_w, rect_h = 842, 412
    rect_x = (w - rect_w) // 2
    rect_y = 150

    thumb      = Image.open(thumb_path).resize((rect_w, rect_h)).convert("RGBA")
    neon_color = random.choice(NEON_COLORS)
    glow       = Image.new("RGBA", (rect_w + 80, rect_h + 80), (0, 0, 0, 0))
    glow_draw  = ImageDraw.Draw(glow)

    for r in range(40, 0, -4):
        alpha = int(255 * (r / 40))
        glow_draw.rectangle(
            (r, r, glow.width - r, glow.height - r),
            outline=(*neon_color, alpha // 2),
            width=4,
        )

    blur_bg.paste(glow, (rect_x - 40, rect_y - 40), glow)
    blur_bg.paste(thumb, (rect_x, rect_y), thumb)

    try:
        title_font = ImageFont.truetype(_F_TITLE, 38)
        meta_font  = ImageFont.truetype(_F_META,  22)
        tag_font   = ImageFont.truetype(_F_TAG,   26)
    except OSError:
        title_font = meta_font = tag_font = ImageFont.load_default()

    title_y = rect_y + rect_h + 40
    text    = trim_to_width(title, title_font, 800)
    try:
        tx = (w - title_font.getlength(text)) // 2
    except AttributeError:
        tx = 40
    draw.text((tx, title_y), text, fill=(255, 255, 255), font=title_font)

    meta_y    = title_y + 50
    meta_text = f"YouTube:{views} |Time:{duration_text} |Player:@{player_username}"
    try:
        mx = (w - meta_font.getlength(meta_text)) // 2
    except AttributeError:
        mx = 40
    draw.text((mx, meta_y), meta_text, fill=neon_color, font=meta_font)

    padding = 25
    dev_tag = "Dev :- @ll_BAD_MUNDA_ll"
    bot_tag = "BadMusic"
    try:
        dev_w = tag_font.getlength(dev_tag)
    except AttributeError:
        dev_w = 200

    draw.text((w - dev_w - padding, padding), dev_tag, fill=neon_color, font=tag_font)
    draw.text((padding, h - 60),              bot_tag, fill=neon_color, font=tag_font)

    try:
        os.remove(thumb_path)
    except OSError:
        pass

    blur_bg.save(cache_path)
    return cache_path
      

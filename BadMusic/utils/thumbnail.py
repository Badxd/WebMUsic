# Copyright (C) 2024 by Badhacker98@Github
# Owner https://t.me/ll_BAD_MUNDA_ll
# Original logic from thumbnails_best_.py — adapted for BadMusic

import os
import re
import random
import aiofiles
import aiohttp

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch

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


async def get_thumb(videoid: str, player_username: str = None) -> str:
    if player_username is None:
        try:
            from BadMusic import app as _app
            me = await _app.get_me()
            player_username = me.username or "BadMusicBot"
        except Exception:
            player_username = "BadMusicBot"

    cache_path = os.path.join(CACHE_DIR, f"{videoid}_v5.png")
    if os.path.exists(cache_path):
        return cache_path

    try:
        results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
        search_result = await results.next()
        data      = search_result.get("result", [])[0]
        title     = re.sub(r"\W+", " ", data.get("title", "Unknown Title")).title()
        thumbnail = data.get("thumbnails", [{}])[0].get("url", config.YOUTUBE_IMG_URL)
        duration  = data.get("duration")
        views     = data.get("viewCount", {}).get("short", "Unknown Views")
    except Exception:
        title, thumbnail, duration, views = "Unknown Title", config.YOUTUBE_IMG_URL, None, "Unknown Views"

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
      

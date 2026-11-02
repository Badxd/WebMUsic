"""
core/utils.py — Shared formatting and helper utilities
"""
import base64
import math
from typing import Optional

from config import MINIAPP_LINK


# ── Time formatting ───────────────────────────────────────
def fmt_sec(sec) -> str:
    try:
        sec = int(float(sec))
    except Exception:
        return "0:00"
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ── Progress bar ──────────────────────────────────────────
def make_progress_bar(played: str, dur: str) -> str:
    try:
        def to_sec(t: str) -> int:
            p = t.strip().split(":")
            return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2]) \
                if len(p) == 3 else int(p[0]) * 60 + int(p[1])
        pct = math.floor((to_sec(played) / to_sec(dur)) * 100)
    except Exception:
        pct = 0
    bars = [
        (0,  10, "◉—————————"), (10, 20, "—◉————————"),
        (20, 30, "——◉———————"), (30, 40, "———◉——————"),
        (40, 50, "————◉—————"), (50, 60, "—————◉————"),
        (60, 70, "——————◉———"), (70, 80, "———————◉——"),
        (80, 95, "————————◉—"), (95, 101, "—————————◉"),
    ]
    # pct == 0 must hit the FIRST bucket (circle at the very start) —
    # "lo < pct" excluded it before, so it fell through to the LAST
    # bucket by accident and showed the bar as if the song had
    # already finished, right from 0:00.
    if pct <= 0:
        return bars[0][2]
    for lo, hi, bar in bars:
        if lo < pct <= hi:
            return bar
    return "—————————◉"


# ── Deep-link encoding ────────────────────────────────────
def encode_chat_id(chat_id: int) -> str:
    return "N" + str(abs(chat_id)) if chat_id < 0 else str(chat_id)


def decode_chat_id(s: str) -> int:
    s = (s or "").strip()
    if s.startswith("N"):
        try:
            return -int(s[1:])
        except ValueError:
            return 0
    try:
        return int(s)
    except ValueError:
        return 0


def make_startapp_link(link: str, title: str, duration: str, chat_id: int = 0) -> str:
    """
    Encode as base64url(link | safe_title | duration | N<abs_chat_id>)
    Replaces '|' in title with '¦' to prevent split corruption.
    """
    cid_str    = encode_chat_id(chat_id)
    safe_title = title.replace("|", "¦")
    raw        = f"{link}|{safe_title}|{duration}|{cid_str}"
    encoded    = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    if len(encoded) > 512:
        for pat in ["v=", "youtu.be/", "shorts/"]:
            if pat in link:
                vid = link.split(pat)[-1].split("&")[0].split("?")[0]
                if len(vid) == 11:
                    raw     = f"ytid:{vid}|{safe_title[:80]}|{duration}|{cid_str}"
                    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
                    break

    return f"{MINIAPP_LINK}?startapp={encoded}"

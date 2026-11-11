"""Canali YouTube: feed RSS ufficiale + Shorts + trascrizione dai sottotitoli.

Se i sottotitoli non sono disponibili (o YouTube blocca il server), si usa la descrizione e
l'item viene marcato con meta.transcript = False.
"""

import asyncio
import json

import feedparser
import httpx
import yt_dlp

from digest.collectors.base import Ctx
from digest.models import Item
from digest.web import UA, clean, is_fresh, iso, parse_date

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
LANG_PREF = ("it-orig", "en-orig", "it", "en")


async def _is_short(client: httpx.AsyncClient, vid: str) -> bool:
    # /shorts/<id> risponde 200 per gli Shorts e reindirizza per i video normali.
    # Il cookie SOCS evita la pagina di consenso cookie europea.
    try:
        r = await client.get(f"https://www.youtube.com/shorts/{vid}", follow_redirects=False,
                             headers={"Cookie": "SOCS=CAI"})
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _transcript(vid: str) -> tuple[str, int | None]:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": _Silent()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    duration = info.get("duration")
    tracks = {**(info.get("automatic_captions") or {}), **(info.get("subtitles") or {})}
    lang = next((l for l in LANG_PREF if l in tracks), None)
    if not lang:
        return "", duration
    url = next((f["url"] for f in tracks[lang] if f.get("ext") == "json3"), None)
    if not url:
        return "", duration
    data = httpx.get(url, headers={"User-Agent": UA}, timeout=30).json()
    words = ["".join(s.get("utf8", "") for s in ev.get("segs", [])) for ev in data.get("events", [])]
    return clean(" ".join(words)), duration


class _Silent:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


async def collect_youtube(ctx: Ctx) -> list[Item]:
    r = await ctx.client.get(FEED.format(ctx.src["channel_id"]))
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    items = []
    for e in feed.entries:
        vid = e.get("yt_videoid")
        published = parse_date(e.get("published_parsed"))
        if not vid or not ctx.is_new(vid) or not is_fresh(published, ctx.since):
            continue
        short = await _is_short(ctx.client, vid)
        try:
            transcript, duration = await asyncio.to_thread(_transcript, vid)
        except Exception:  # YouTube può bloccare: si ripiega sulla descrizione
            transcript, duration = "", None
        description = clean(e.get("media_description") or e.get("summary", ""))
        items.append(ctx.item(
            kind="short" if short else "video",
            title=e.get("title", "").strip(),
            url=f"https://www.youtube.com/shorts/{vid}" if short else f"https://www.youtube.com/watch?v={vid}",
            published=iso(published),
            summary=description[:400],
            content=(transcript or description)[:15000],
            key=vid,
            meta={"creator": ctx.src["creator"], "transcript": bool(transcript), "duration": duration},
        ))
    return ctx.cap(items)

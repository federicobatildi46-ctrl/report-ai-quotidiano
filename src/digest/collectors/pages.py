"""Pagine web senza feed: sitemap con date e pagine di release notes / changelog a sezioni."""

import asyncio
import re
from datetime import timedelta
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from digest.collectors.base import Ctx
from digest.models import Item
from digest.web import clean, extract_article, find_date, is_fresh, iso, parse_date

URL_RE = re.compile(r"<url>(.*?)</url>", re.S)
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
LASTMOD_RE = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>")
GRACE_DAYS = 1    # tolleranza tra data di pubblicazione dichiarata e finestra di raccolta


def _matches(url: str, include: list[str], exclude: list[str]) -> bool:
    return any(p in url for p in include) and not any(p in url for p in exclude)


async def _sitemap_entries(ctx: Ctx, url: str) -> list[tuple[str, str | None]]:
    r = await ctx.client.get(url)
    r.raise_for_status()
    if "<sitemapindex" in r.text:
        children = [l for l in LOC_RE.findall(r.text) if _matches(l, ctx.src.get("child_include", [""]), [])]
        nested = await asyncio.gather(*(_sitemap_entries(ctx, c) for c in children))
        return [e for sub in nested for e in sub]
    out = []
    for block in URL_RE.findall(r.text):
        loc = LOC_RE.search(block)
        if loc:
            lm = LASTMOD_RE.search(block)
            out.append((loc.group(1), lm.group(1) if lm else None))
    return out


async def collect_sitemap(ctx: Ctx) -> list[Item]:
    include, exclude = ctx.src.get("include", [""]), ctx.src.get("exclude", [])
    fresh = []
    for loc, lastmod in await _sitemap_entries(ctx, ctx.src["url"]):
        if urlparse(loc).path in ("", "/"):   # la homepage cambia sempre, non è una notizia
            continue
        if not _matches(loc, include, exclude) or not ctx.is_new(loc):
            continue
        d = parse_date(lastmod)
        if is_fresh(d, ctx.since) or (d is None and ctx.initialized):
            fresh.append((loc, d))
    fresh = fresh[: ctx.src.get("max_items", 12)]

    async def enrich(loc, lastmod) -> Item | None:
        r = await ctx.client.get(loc)
        if r.status_code != 200:
            return None
        art = extract_article(r.text)
        if ctx.excluded(art["title"]):
            return None
        # Pagina con una data di pubblicazione vecchia ma "ritoccata" di recente: non è una novità.
        if art["published"] and not is_fresh(art["published"], ctx.since - timedelta(days=GRACE_DAYS)):
            return None
        # Prima esecuzione: senza una data dichiarata dalla pagina non sappiamo se è nuova
        # (la lastmod cambia anche per ritocchi). Dal giorno dopo vale "URL nuovo = novità".
        if not ctx.initialized and art["published"] is None:
            return None
        pub = art["published"] or lastmod
        return ctx.item(kind=ctx.src.get("kind", "article"), title=art["title"] or loc, url=loc,
                        published=iso(pub), summary=art["description"][:400], content=art["text"],
                        key=loc, meta={"lastmod": iso(lastmod)})

    results = await asyncio.gather(*(enrich(l, d) for l, d in fresh), return_exceptions=True)
    return ctx.cap([r for r in results if isinstance(r, Item)])


def _level(tag: Tag) -> int:
    return int(tag.name[1])


def _section_after(heading: Tag) -> str:
    """Testo che segue un titolo fino al titolo successivo di pari livello o superiore."""
    node = heading
    while node.find_next_sibling() is None and node.parent is not None:
        node = node.parent
    parts = []
    for sib in node.find_next_siblings():
        h = sib if sib.name and re.fullmatch(r"h[1-6]", sib.name) else sib.find(re.compile(r"^h[1-6]$"))
        if h is not None and _level(h) <= _level(heading):
            break
        parts.append(sib.get_text(" "))
    return clean(" ".join(parts))


def _card(heading: Tag) -> Tag:
    """Il contenitore più grande che include solo questo titolo (la 'card' della voce)."""
    node = heading
    while node.parent is not None and len(node.parent.find_all(heading.name)) == 1:
        node = node.parent
    return node


async def collect_sections(ctx: Ctx) -> list[Item]:
    r = await ctx.client.get(ctx.src["url"])
    r.raise_for_status()
    page_url = str(r.url)
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for h in soup.find_all(ctx.src.get("heading", "h3")):
        heading = clean(h.get_text(" "))
        if not heading:
            continue
        date_in_heading = find_date(heading)
        if date_in_heading:
            d, text, title = date_in_heading, _section_after(h), f"{ctx.src['name']} — {heading}"
        else:
            card_text = clean(_card(h).get_text(" "))
            d, text, title = find_date(card_text), card_text, heading
        key = f"{page_url}#{heading}"
        if not text or not ctx.is_new(key) or ctx.excluded(heading):
            continue
        if not (is_fresh(d, ctx.since) or (d is None and ctx.initialized)):
            continue
        anchor = h.get("id")
        items.append(ctx.item(kind=ctx.src.get("kind", "changelog"), title=title,
                              url=f"{page_url}#{anchor}" if anchor else page_url,
                              published=iso(d), summary=text[:400], content=text[:6000], key=key))
    return ctx.cap(items)

"""Feed RSS/Atom e release GitHub (con il dettaglio preso dal CHANGELOG)."""

import asyncio
import re

import feedparser

from digest.collectors.base import Ctx
from digest.models import Item
from digest.web import extract_article, html_to_text, is_fresh, iso, parse_date

SHORT_TEXT = 600   # sotto questa lunghezza il feed dà solo un estratto: scarichiamo l'articolo
NO_FETCH_KINDS = {"commit", "incident", "release"}


async def _fetch_full(ctx: Ctx, item: Item) -> None:
    try:
        r = await ctx.client.get(item.url)
        if r.status_code == 200:
            art = extract_article(r.text)
            if len(art["text"]) > len(item.content):
                item.content = art["text"]
                item.summary = art["description"][:400] or item.summary
    except Exception:
        pass  # resta l'estratto del feed


async def collect_feed(ctx: Ctx) -> list[Item]:
    items = await _feed_items(ctx)
    if ctx.src.get("fetch_full", True):
        short = [i for i in items if len(i.content) < SHORT_TEXT and i.kind not in NO_FETCH_KINDS]
        await asyncio.gather(*(_fetch_full(ctx, i) for i in short))
    return items


async def _feed_items(ctx: Ctx) -> list[Item]:
    r = await ctx.client.get(ctx.src["url"])
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    kind = ctx.src.get("kind", "article")
    items = []
    for e in feed.entries:
        link = e.get("link", "")
        key = e.get("id") or link
        published = parse_date(e.get("published_parsed") or e.get("updated_parsed"))
        if not ctx.is_new(key) or not is_fresh(published, ctx.since) or ctx.excluded(e.get("title", "")):
            continue
        body = e.get("content", [{}])[0].get("value") or e.get("summary", "")
        text = html_to_text(body)
        items.append(ctx.item(kind=kind, title=e.get("title", "").strip(), url=link,
                              published=iso(published), summary=text[:400], content=text, key=key,
                              meta={"comments": e.get("comments")} if e.get("comments") else {}))
    return ctx.cap(items)


async def collect_hackernews(ctx: Ctx) -> list[Item]:
    """Storie di Hacker News sulla query, con un minimo di punti (API Algolia, ufficiale e gratuita)."""
    r = await ctx.client.get("https://hn.algolia.com/api/v1/search_by_date", params={
        "query": ctx.src["query"], "tags": "story", "hitsPerPage": 50,
        "numericFilters": f"points>={ctx.src.get('min_points', 100)},"
                          f"created_at_i>={int(ctx.since.timestamp())}"})
    r.raise_for_status()
    items = []
    for hit in r.json().get("hits", []):
        hn_url = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        url = hit.get("url") or hn_url
        if not ctx.is_new(hit["objectID"]):
            continue
        items.append(ctx.item(kind="article", title=hit.get("title", ""), url=url,
                              published=hit.get("created_at"), summary="", content="",
                              key=hit["objectID"],
                              meta={"points": hit.get("points"), "comments": hn_url}))
    items = ctx.cap(items)
    await asyncio.gather(*(_fetch_full(ctx, i) for i in items if i.url != i.meta["comments"]))
    return items


def _changelog_sections(md: str) -> dict[str, str]:
    """'## 2.1.322' → testo della sezione."""
    sections, current, buf = {}, None, []
    for line in md.splitlines():
        m = re.match(r"^##\s+v?(\d+\.\d+\.\d+)", line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            current, buf = m.group(1), []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


async def collect_github_releases(ctx: Ctx) -> list[Item]:
    items = await _feed_items(ctx)
    for it in items:
        it.kind = "release"
    if not items or not ctx.src.get("changelog_url"):
        return items
    r = await ctx.client.get(ctx.src["changelog_url"])
    sections = _changelog_sections(r.text) if r.status_code == 200 else {}
    for it in items:
        version = it.title.lstrip("v").strip()
        notes = sections.get(version)
        if notes:
            it.content = notes[:6000]
            it.summary = notes[:400]
    return items

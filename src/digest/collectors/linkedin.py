"""Post LinkedIn pubblici dei creator, via Apify (attore harvestapi/linkedin-profile-posts).

Costo: ~0,002 $ a post. Con 2 profili e massimo 5 post a testa al giorno, pochi centesimi al mese.
"""

import os

from digest.collectors.base import Ctx
from digest.models import Item
from digest.web import clean, is_fresh, iso, parse_date

ACTOR = "harvestapi~linkedin-profile-posts"


def _get(d: dict, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return d if d is not None else default


async def collect_linkedin(ctx: Ctx) -> list[Item]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_TOKEN mancante in .env")
    profiles = ctx.src["profiles"]
    r = await ctx.client.post(
        f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items",
        params={"timeout": 240},
        headers={"Authorization": f"Bearer {token}"},
        json={"targetUrls": [p["url"] for p in profiles], "maxPosts": ctx.src.get("max_posts", 5),
              "postedLimit": "24h", "includeReposts": False, "scrapeReactions": False,
              "scrapeComments": False},
        timeout=300,
    )
    r.raise_for_status()
    names = {p["url"].rstrip("/").split("/")[-1]: p["name"] for p in profiles}

    items = []
    for post in r.json():
        url = post.get("linkedinUrl") or post.get("url") or ""
        text = clean(post.get("content") or post.get("text") or "")
        published = parse_date(_get(post, "postedAt", "date") or post.get("postedAt"))
        if not url or not text or not ctx.is_new(url) or not is_fresh(published, ctx.since):
            continue
        author_url = _get(post, "author", "linkedinUrl", default="")
        handle = author_url.rstrip("/").split("/")[-1] if author_url else ""
        creator = names.get(handle) or _get(post, "author", "name", default="LinkedIn")
        items.append(ctx.item(kind="post", title=f"{creator}: {text[:80]}…", url=url,
                              published=iso(published), summary=text[:400], content=text[:6000],
                              key=url, meta={"creator": creator}))
    return items

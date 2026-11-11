"""GitHub: ricerca di repo nuove per area dell'agenzia + GitHub Trending del giorno."""

import asyncio
import os
import re
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup

from digest.collectors.base import Ctx
from digest.models import Item
from digest.web import clean

API = "https://api.github.com"

# Repo spazzatura tipiche (crack, attivatori, cheat) spesso gonfiate con stelle finte.
SPAM_RE = re.compile(r"activat|crack|keygen|cheat|spoofer|aimbot|executor|mod[ -]?menu|robux|"
                     r"injector|license[ -]?key|serial[ -]?key|free[ -]download|unlocker|premium|"
                     r"full[ -]version|pro[ -]?version|for[ -]windows|\bapk\b", re.I)
README_SPAM_RE = re.compile(r"download\S*\s.{0,200}\.(zip|rar|7z|exe|msi)\b", re.I | re.S)
MIN_README = 300
SAME_STARS_LIMIT = 3   # ≥3 repo nuove con lo stesso identico numero di stelle = rete di bot


def _drop_spam(found: dict[str, tuple[str, dict]]) -> dict[str, tuple[str, dict]]:
    stars = Counter(repo["stargazers_count"] for _, repo in found.values())
    clean_found = {}
    for name, (area, repo) in found.items():
        text = f"{name} {repo.get('description') or ''}"
        if repo.get("fork") or repo.get("archived") or SPAM_RE.search(text):
            continue
        if stars[repo["stargazers_count"]] >= SAME_STARS_LIMIT:
            continue
        if not repo.get("description"):
            continue
        clean_found[name] = (area, repo)
    return clean_found


def github_token() -> str | None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token
    if shutil.which("gh"):
        try:
            out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
            return out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None
    return None


async def collect_github_search(ctx: Ctx) -> list[Item]:
    token = github_token()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    since = (datetime.now(UTC) - timedelta(days=ctx.src.get("created_within_days", 7))).date().isoformat()
    min_stars = ctx.src.get("min_stars", 25)
    per_area = ctx.src.get("max_per_area", 4)

    found: dict[str, tuple[str, dict]] = {}
    for area, queries in ctx.src["queries"].items():
        for q in queries:
            r = await ctx.client.get(f"{API}/search/repositories", headers=headers, params={
                "q": f"{q.format(since=since)} stars:>={min_stars}",
                "sort": "stars", "order": "desc", "per_page": 10})
            if r.status_code != 200:
                raise RuntimeError(f"GitHub search {r.status_code}: {r.text[:120]}")
            for repo in r.json().get("items", []):
                found.setdefault(repo["full_name"], (area, repo))
            await asyncio.sleep(0.3)

    found = _drop_spam(found)
    by_area: dict[str, list[dict]] = {}
    for name, (area, repo) in found.items():
        if ctx.is_new(name):
            by_area.setdefault(area, []).append(repo)

    items = []
    for area, repos in by_area.items():
        repos.sort(key=lambda x: x["stargazers_count"], reverse=True)
        kept = 0
        for repo in repos:
            if kept >= per_area:
                break
            rr = await ctx.client.get(f"{API}/repos/{repo['full_name']}/readme",
                                      headers={**headers, "Accept": "application/vnd.github.raw"})
            readme = rr.text if rr.status_code == 200 else ""
            if len(readme) < MIN_README or README_SPAM_RE.search(readme):
                continue   # README vuoto o che invita a scaricare eseguibili: scarto
            readme = readme[:4000]
            kept += 1
            desc = repo.get("description") or ""
            items.append(ctx.item(
                kind="repo", subsection=area, title=repo["full_name"], url=repo["html_url"],
                published=repo.get("created_at"), summary=desc[:400],
                content=f"{desc}\n\nREADME:\n{readme}", key=repo["full_name"],
                meta={"stars": repo["stargazers_count"], "language": repo.get("language"),
                      "topics": repo.get("topics", []), "area": area}))
    return items


async def collect_github_trending(ctx: Ctx) -> list[Item]:
    r = await ctx.client.get(ctx.src["url"])
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for row in soup.select("article.Box-row"):
        a = row.select_one("h2 a")
        if not a:
            continue
        name = clean(a.get_text("")).replace(" ", "")
        if not ctx.is_new(name):
            continue
        desc = clean(row.select_one("p").get_text(" ")) if row.select_one("p") else ""
        lang = row.select_one('[itemprop="programmingLanguage"]')
        today = next((clean(s.get_text(" ")) for s in row.select("span") if "stars today" in s.get_text()), "")
        items.append(ctx.item(
            kind="repo", subsection="trending", title=name, url=f"https://github.com/{name}",
            published=datetime.now(UTC).isoformat(), summary=desc, content=desc, key=name,
            meta={"language": clean(lang.get_text()) if lang else None, "stars_today": today}))
    items = items[: ctx.src.get("max_items", 15)]

    # README: senza, Claude ha solo una riga di descrizione e non può dire a cosa serve
    token = github_token()
    headers = {"Accept": "application/vnd.github.raw"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def add_readme(it: Item):
        rr = await ctx.client.get(f"{API}/repos/{it.title}/readme", headers=headers)
        if rr.status_code == 200:
            it.content = f"{it.summary}\n\nREADME:\n{rr.text[:4000]}"

    await asyncio.gather(*(add_readme(i) for i in items), return_exceptions=True)
    return items

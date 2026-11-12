"""Fase 7 — la voce di Federico: scarica i suoi post LinkedIn (Apify) e ne ricava una guida di
stile (config/voice/federico_voice.md) che i generatori di post e Shorts usano sempre.

Rilanciare `uv run digest voice` quando ha pubblicato nuovi post.
"""

import json
import os
from datetime import UTC, datetime

import httpx

from digest import CONFIG_DIR, PROMPTS_DIR
from digest.claude import run_claude
from digest.sources import load_config

VOICE_DIR = CONFIG_DIR / "voice"
SAMPLES = VOICE_DIR / "samples" / "linkedin_posts.json"
GUIDE = VOICE_DIR / "federico_voice.md"
ACTOR = "harvestapi~linkedin-profile-posts"


def fetch_posts(max_posts: int = 40) -> list[dict]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_TOKEN mancante in .env")
    profile = load_config()["me"]["linkedin"]
    r = httpx.post(f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items",
                   params={"timeout": 240}, headers={"Authorization": f"Bearer {token}"},
                   json={"targetUrls": [profile], "maxPosts": max_posts, "includeReposts": False,
                         "scrapeReactions": False, "scrapeComments": False}, timeout=300)
    r.raise_for_status()
    posts = [p for p in r.json() if (p.get("content") or "").strip()]
    SAMPLES.parent.mkdir(parents=True, exist_ok=True)
    SAMPLES.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
    return posts


def build_guide(posts: list[dict], model: str = "sonnet") -> tuple[str, dict]:
    blocks = "\n\n---\n\n".join(
        f"POST del {((p.get('postedAt') or {}).get('date') or '')[:10]}:\n{p['content'].strip()}"
        for p in posts)
    prompt = (PROMPTS_DIR / "voice_guide.md").read_text(encoding="utf-8").replace("{{POSTS}}", blocks)
    schema = {"type": "object", "properties": {"markdown": {"type": "string"}}, "required": ["markdown"]}
    out, stats = run_claude(prompt, schema, model=model, timeout=900,
                            system="Sei un esperto di copywriting e analisi dello stile. Rispondi "
                                   "solo con dati conformi allo schema JSON.")
    header = (f"# La voce di Federico — guida di stile\n\n"
              f"*Ricavata da {len(posts)} post LinkedIn il "
              f"{datetime.now(UTC).date().isoformat()}. Rigenera con `uv run digest voice`.*\n\n")
    body = out["markdown"].strip()
    if body.startswith("# "):           # il titolo lo mettiamo noi
        body = body.split("\n", 1)[1].strip() if "\n" in body else ""
    GUIDE.write_text(header + body + "\n", encoding="utf-8")
    return GUIDE.read_text(encoding="utf-8"), stats

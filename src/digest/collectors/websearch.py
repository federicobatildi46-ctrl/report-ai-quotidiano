"""Ricerca online fatta da Claude (WebSearch), per la sezione "Da provare": repo, skill, connettori
e tool AI che stanno girando in rete e che chiunque può provare subito.

Claude restituisce solo candidati con URL diretto (repo o sito ufficiale); il codice scarta i già
visti (memoria per URL) e quelli già usciti negli ultimi report, poi la build testa ogni link.
"""

import asyncio
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

from digest import PROMPTS_DIR, REPORTS_DIR
from digest.claude import run_claude
from digest.collectors.base import Ctx
from digest.models import Item

SCHEMA = {
    "type": "object",
    "properties": {"finds": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "url": {"type": "string"},
            "category": {"type": "string", "enum": ["repo", "skill", "connettori", "app"]},
            "what": {"type": "string"},
            "how_to_try": {"type": "string"},
            "cost": {"type": "string"},
            "evidence": {"type": "string"},
            "date": {"type": "string"},
        },
        "required": ["name", "url", "category", "what", "how_to_try", "evidence"],
    }}},
    "required": ["finds"],
}
SYSTEM = ("Fai ricerche online per un report AI personale in italiano. Rispondi solo con dati "
          "conformi allo schema JSON. Riporta solo cose che hai trovato davvero, con URL reali.")


def _norm(url: str) -> str:
    p = urlparse(url.strip())
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/').lower()}"


def recent_finds(days: int = 5) -> list[str]:
    """Titoli già usciti nella sezione negli ultimi report: Claude non deve riproporli."""
    out = []
    for p in sorted(REPORTS_DIR.glob("????-??-??.json"))[-days:]:
        try:
            report = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for sec in report.get("sections", []):
            if sec["id"] == "virali":
                out += [f"{it['title']} ({it['primary_url']})" for it in sec["items"]]
    return out


async def collect_websearch(ctx: Ctx) -> list[Item]:
    today = datetime.now(UTC).date().isoformat()
    already = recent_finds()
    prompt = ((PROMPTS_DIR / "web_research.md").read_text(encoding="utf-8")
              .replace("{{TODAY}}", today)
              .replace("{{SINCE}}", ctx.since.date().isoformat())
              .replace("{{MAX}}", str(ctx.src.get("max_items", 8)))
              .replace("{{ALREADY}}", "\n".join(f"- {a}" for a in already) or "- (niente)"))
    out, _ = await asyncio.to_thread(
        run_claude, prompt, SCHEMA, system=SYSTEM, model=ctx.src.get("model", "sonnet"),
        timeout=ctx.src.get("timeout", 300), tools=["WebSearch", "WebFetch"])

    items = []
    for f in out["finds"]:
        url = f["url"].strip()
        if not url.startswith("http") or not ctx.is_new(_norm(url)):
            continue
        is_repo = "github.com/" in url and len(urlparse(url).path.strip("/").split("/")) == 2
        body = (f"{f['what']}\n\nCOME SI PROVA: {f['how_to_try']}\n"
                f"COSTO: {f.get('cost') or 'non indicato'}\n"
                f"PERCHÉ STA GIRANDO (dalla ricerca web, da verificare): {f['evidence']}")
        items.append(ctx.item(kind="repo" if is_repo else "tool", subsection=f["category"],
                              title=f["name"], url=url, published=f.get("date") or today,
                              summary=f["what"][:400], content=body, key=_norm(url),
                              meta={"area": f["category"]}))
    return items[: ctx.src.get("max_items", 8)]

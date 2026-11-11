"""Fase 5/6 — generatori on-demand: lezione, post LinkedIn, script Shorts.

Per ogni notizia riscarica il contenuto completo delle fonti (i dati grezzi del cloud non sono
sul PC): articoli → testo della pagina, YouTube → trascrizione, GitHub → README, LinkedIn → solo
il riassunto (blocca i bot). Poi chiama Claude e salva il risultato in outputs/.
"""

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from digest import CONFIG_DIR, OUTPUTS_DIR, PROMPTS_DIR, REPORTS_DIR
from digest.claude import run_claude
from digest.collectors.github import github_token
from digest.collectors.youtube import _transcript
from digest.web import extract_article, make_client

KINDS = {
    "lezione": {"dir": "lezioni", "prompt": "lesson.md", "label": "Lezione"},
    "post": {"dir": "linkedin", "prompt": "linkedin_post.md", "label": "Post LinkedIn"},
    "short": {"dir": "shorts", "prompt": "youtube_short.md", "label": "Script Shorts"},
}
VOICE_PATH = CONFIG_DIR / "voice" / "federico_voice.md"
NO_VOICE = ("Guida di stile non ancora disponibile (arriva in Fase 7). Scrivi in prima persona, "
            "italiano diretto e colloquiale, da persona che sta imparando e condivide cosa scopre: "
            "pratico, onesto, niente tono da guru.")
SOURCE_CHARS = 8000
SCHEMA = {"type": "object",
          "properties": {"title": {"type": "string"}, "markdown": {"type": "string"}},
          "required": ["title", "markdown"]}
SYSTEM = ("Scrivi contenuti in italiano per Federico. Rispondi solo con dati conformi allo schema "
          "JSON. Nel campo markdown metti il contenuto completo. Non inventare fatti.")


def _topics() -> dict:
    with open(CONFIG_DIR / "topics.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_item(date: str, item_id: str) -> dict:
    report = json.loads((REPORTS_DIR / f"{date}.json").read_text(encoding="utf-8"))
    for sec in report["sections"]:
        for it in sec["items"]:
            if it["id"] == item_id:
                return it
    raise KeyError(f"notizia {item_id} non trovata nel report del {date}")


def output_path(kind: str, item_id: str) -> Path:
    return OUTPUTS_DIR / KINDS[kind]["dir"] / f"{item_id}.md"


def existing_outputs(date: str) -> dict[str, list[str]]:
    """item_id → tipi già generati, per il report di una data."""
    found: dict[str, list[str]] = {}
    for kind, k in KINDS.items():
        for p in (OUTPUTS_DIR / k["dir"]).glob(f"{date}-*.md"):
            found.setdefault(p.stem, []).append(kind)
    return found


async def _source_text(client, src: dict) -> str:
    url = src["url"]
    try:
        if "youtube.com/" in url:
            vid = re.search(r"(?:v=|shorts/)([\w-]{6,})", url)
            if vid:
                text, _ = await asyncio.to_thread(_transcript, vid.group(1))
                if text:
                    return "TRASCRIZIONE: " + text
        m = re.match(r"https://github\.com/([^/]+/[^/#?]+)/?$", url)
        if m:
            headers = {"Accept": "application/vnd.github.raw"}
            if token := github_token():
                headers["Authorization"] = f"Bearer {token}"
            r = await client.get(f"https://api.github.com/repos/{m.group(1)}/readme", headers=headers)
            if r.status_code == 200:
                return "README: " + r.text
        if "linkedin.com/" in url:
            return ""
        r = await client.get(url)
        if r.status_code == 200:
            return extract_article(r.text, limit=SOURCE_CHARS)["text"]
    except Exception:
        pass
    return ""


async def gather_sources(item: dict, limit: int) -> list[dict]:
    srcs = item["sources"][:limit]
    async with make_client() as client:
        texts = await asyncio.gather(*(_source_text(client, s) for s in srcs))
    return [{**s, "text": t[:SOURCE_CHARS]} for s, t in zip(srcs, texts)]


def _fill(template: str, **values) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def generate(date: str, item_id: str, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"tipo sconosciuto: {kind}")
    topics = _topics()
    gen_cfg = topics.get("generators") or {}
    item = find_item(date, item_id)
    sources = asyncio.run(gather_sources(item, gen_cfg.get("max_sources", 4)))

    src_block = "\n\n---\n\n".join(
        f"FONTE: {s['name']} ({'ufficiale' if s['official'] else 'non ufficiale'})\n"
        f"TITOLO: {s['title']}\nCONTENUTO: {s['text'] or '(non scaricabile: usa solo il riassunto)'}"
        for s in sources)
    voice = VOICE_PATH.read_text(encoding="utf-8") if VOICE_PATH.exists() else NO_VOICE
    prompt = _fill((PROMPTS_DIR / KINDS[kind]["prompt"]).read_text(encoding="utf-8"),
                   DATE=date, TITLE=item["title"], SUMMARY=item["summary"],
                   KEY_POINTS="\n".join(f"- {p}" for p in item.get("key_points", [])),
                   WHY=item["why"], PROFILE=topics["profile"].strip(), VOICE=voice,
                   SOURCES=src_block)
    out, stats = run_claude(prompt, SCHEMA, system=SYSTEM, model=gen_cfg.get("model", "sonnet"),
                            timeout=900)

    fonti = "\n".join(f"- [{s['name']}]({s['url']})" for s in item["sources"])
    meta = {"tipo": KINDS[kind]["label"], "notizia": item["title"], "report": date,
            "generato": datetime.now(UTC).isoformat(timespec="seconds"),
            "modello": gen_cfg.get("model", "sonnet")}
    front = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n"
    body = f"# {out['title']}\n\n{out['markdown'].strip()}\n\n## Fonti della notizia\n\n{fonti}\n"
    path = output_path(kind, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(front + body, encoding="utf-8")
    return path


def read_output(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---\n"):
        _, fm, body = text.split("---\n", 2)
        meta = yaml.safe_load(fm) or {}
    return {"meta": meta, "markdown": body.strip()}

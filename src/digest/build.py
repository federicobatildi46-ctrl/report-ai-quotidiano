"""Fase 2 — dal materiale raccolto al report: selezione → scrittura → verifica link → salvataggio.

1. SELEZIONE (Claude): vede titoli ed estratti di tutto, scarta il rumore, raggruppa gli elementi
   che parlano della stessa cosa in "storie", assegna sezione e priorità.
2. SCRITTURA (Claude): per ogni storia riceve il contenuto completo delle fonti e scrive titolo,
   riassunto, "perché ti serve" e badge di fact check.
3. CONTROLLI (Python, deterministici): i link vengono dalle fonti raccolte (Claude non scrive mai
   URL), vengono testati uno per uno; il badge viene corretto se non è coerente con le fonti.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from urllib.parse import urlparse

import httpx
import yaml

from digest import CONFIG_DIR, DATA_DIR, PROMPTS_DIR, REPORTS_DIR, feedback
from digest.claude import run_claude
from digest.sources import load_config
from digest.web import make_client, to_json

RAW_DIR = DATA_DIR / "raw"
BADGES = ["ufficiale", "confermata", "da_verificare", "smentita"]
# siti che rifiutano i robot: il link funziona nel browser ma non si può testare da qui
UNVERIFIABLE_HOSTS = ("linkedin.com", "reddit.com", "x.com", "twitter.com", "producthunt.com")
WRITE_ATTEMPTS = 3          # la scrittura viene controllata e, se incompleta, rifatta


class BuildError(RuntimeError):
    """Il report non ha superato i controlli di qualità: meglio non inviarlo e riprovare."""
SYSTEM = ("Sei il redattore di un report di notizie AI personale, in italiano. Rispondi solo con "
          "dati conformi allo schema JSON richiesto. Non inventare nulla che non sia nelle fonti.")

TRIAGE_CHARS = 260          # estratto per elemento nella selezione
CONTENT_CHARS = 3500        # contenuto per elemento nella scrittura
TRANSCRIPT_CHARS = 6000     # le trascrizioni video valgono di più


def _topics() -> dict:
    with open(CONFIG_DIR / "topics.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fill(template: str, **values) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {l}" for l in lines)


def _sections_text(topics: dict) -> str:
    out = []
    for s in topics["sections"]:
        subs = ", ".join(f"`{k}` ({v})" for k, v in (s.get("subsections") or {}).items())
        out.append(f"- `{s['id']}` — {s['title']} (max {s['max_items']})"
                   + (f": {s['focus']}" if s.get("focus") else "")
                   + (f". Sottosezioni: {subs}" if subs else ""))
    return "\n".join(out)


def _is_official_url(url: str, domains: list[str]) -> bool:
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.lower().strip("/").split("/")
    for d in domains:
        d = d.lower()
        if "/" in d:
            d_host, *d_path = d.strip("/").split("/")
            if host == d_host and path[:len(d_path)] == d_path:
                return True
        elif host == d or host.endswith("." + d):
            return True
    return False


def publisher(src: dict) -> str:
    """Chi parla davvero: due contenuti dello stesso creator (YouTube + LinkedIn) o dello stesso
    sito NON sono due fonti indipendenti."""
    creator = (src.get("meta") or {}).get("creator")
    if creator:
        return f"creator:{creator.lower()}"
    u = urlparse(src["url"])
    host = u.netloc.lower().removeprefix("www.")
    if host == "github.com":
        return "github.com/" + u.path.strip("/").split("/")[0].lower()
    return ".".join(host.split(".")[-2:])


def prepare(items: list[dict]) -> None:
    """Etichette brevi e ufficialità per dominio (valgono anche per raccolte vecchie)."""
    cfg = load_config()
    labels, domains = cfg.get("labels") or {}, cfg.get("official_domains") or []
    for it in items:
        creator = (it.get("meta") or {}).get("creator")
        if it["kind"] in ("video", "short") and creator:
            it["label"] = f"YouTube · {creator}"
        elif it["kind"] == "post" and creator:
            it["label"] = f"LinkedIn · {creator}"
        else:
            it["label"] = labels.get(it["source_id"], it["source_name"])
        if not it["official"] and _is_official_url(it["url"], domains):
            # es. un post di Hacker News che rimanda a claude.com: il link è la fonte ufficiale
            it["official"] = True
            it["label"] = f"{urlparse(it['url']).netloc.removeprefix('www.')} (via {it['label']})"


def _meta_line(it: dict) -> str:
    m = it.get("meta") or {}
    bits = []
    for k in ("creator", "stars", "stars_today", "area", "points", "language"):
        if m.get(k):
            bits.append(f"{k}={m[k]}")
    if it["kind"] in ("video", "short") and m.get("duration"):
        bits.append(f"durata={m['duration']}s")
    return " ".join(bits)


# ---------- dati verificati su GitHub ----------

REPO_RE = __import__("re").compile(r"^https://github\.com/([^/]+/[^/#?]+?)(?:\.git)?/?(?:[#?].*)?$")


async def repo_facts(urls: list[str]) -> dict[str, dict]:
    """url → dati letti ORA dall'API di GitHub (stelle, date, licenza). Sono fatti verificati:
    sostituiscono i numeri di popolarità riportati da creator, aggregatori o ricerca web."""
    from digest.collectors.github import github_token

    headers = {"Accept": "application/vnd.github+json"}
    if token := github_token():
        headers["Authorization"] = f"Bearer {token}"

    async def one(client, url):
        m = REPO_RE.match(url)
        if not m:
            return url, None
        try:
            r = await client.get(f"https://api.github.com/repos/{m.group(1)}", headers=headers)
            if r.status_code != 200:
                return url, None
            d = r.json()
            return url, {"stars": d.get("stargazers_count"), "created": (d.get("created_at") or "")[:10],
                         "pushed": (d.get("pushed_at") or "")[:10],
                         "license": (d.get("license") or {}).get("spdx_id") or "",
                         "archived": bool(d.get("archived")), "owner": d["owner"]["login"],
                         "owner_type": d["owner"].get("type", "")}
        except (httpx.HTTPError, KeyError, ValueError):
            return url, None

    async with make_client() as client:
        found = await asyncio.gather(*(one(client, u) for u in dict.fromkeys(urls)))
    return {u: f for u, f in found if f}


def _facts_line(f: dict) -> str:
    bits = [f"{f['stars']:,} stelle".replace(",", "."), f"creata il {f['created']}",
            f"ultimo aggiornamento {f['pushed']}"]
    if f["license"] and f["license"] != "NOASSERTION":
        bits.append(f"licenza {f['license']}")
    if f["archived"]:
        bits.append("ARCHIVIATA (non più mantenuta)")
    return "DATI VERIFICATI SU GITHUB ORA: " + " · ".join(bits)


# ---------- 1. selezione ----------

def triage_schema(topics: dict) -> dict:
    return {
        "type": "object",
        "properties": {"stories": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "enum": [s["id"] for s in topics["sections"]]},
                "subsection": {"type": "string"},
                "item_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "priority": {"type": "integer", "minimum": 1, "maximum": 3},
                "reason": {"type": "string"},
            },
            "required": ["section", "subsection", "item_ids", "priority", "reason"],
        }}},
        "required": ["stories"],
    }


def triage(items: list[dict], topics: dict, date: str, model: str) -> tuple[list[dict], dict]:
    lines = []
    for it in items:
        summary = (it["summary"] or it["content"])[:TRIAGE_CHARS].replace("\n", " ")
        lines.append(f"[{it['id']}] ({it['section']} · {it['label']} · {it['kind']}"
                     f"{' · UFFICIALE' if it['official'] else ''} · {(it['published'] or '')[:10]}"
                     f"{' · ' + _meta_line(it) if _meta_line(it) else ''})\n"
                     f"    {it['title']}\n    {summary}")
    prompt = _fill((PROMPTS_DIR / "triage.md").read_text(encoding="utf-8"),
                   DATE=date, PROFILE=topics["profile"].strip(), SECTIONS=_sections_text(topics),
                   MAX_STORIES=str(topics["report"]["max_stories"]),
                   SIGNAL=_bullets(topics["signal"]), NOISE=_bullets(topics["noise"]),
                   PREFERENCES=feedback.prompt_block(), ITEMS="\n".join(lines))
    out, stats = run_claude(prompt, triage_schema(topics), system=SYSTEM, model=model)

    # pulizia deterministica: id esistenti, nessun elemento in due storie, tetti rispettati
    known, used, stories = {it["id"] for it in items}, set(), []
    for st in sorted(out["stories"], key=lambda s: s["priority"]):
        ids = [i for i in dict.fromkeys(st["item_ids"]) if i in known and i not in used]
        if ids:
            used.update(ids)
            stories.append({**st, "item_ids": ids})
    caps = {s["id"]: s["max_items"] for s in topics["sections"]}
    counted: dict[str, int] = {}
    capped = []
    for st in stories:
        counted[st["section"]] = counted.get(st["section"], 0) + 1
        if counted[st["section"]] <= caps[st["section"]] and len(capped) < topics["report"]["max_stories"]:
            capped.append(st)
    return capped, stats


# ---------- 2. scrittura ----------

def write_schema(n: int) -> dict:
    return {
        "type": "object",
        "properties": {
            # niente vincoli rigidi sul numero: se la risposta non li rispetta, Claude Code la fa
            # rigenerare (token sprecati). Le differenze le sistema il codice.
            "in_breve": {"type": "array", "items": {"type": "string"}},
            "stories": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "story": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "why": {"type": "string"},
                    "badge": {"type": "string", "enum": BADGES},
                    "badge_note": {"type": "string"},
                    "subsection": {"type": "string"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 3},
                    "short_hook": {"type": "string"},   # solo sezione "virali"
                },
                "required": ["story", "title", "summary", "key_points", "why", "badge", "badge_note",
                             "subsection", "importance"],
            }},
        },
        "required": ["in_breve", "stories"],
    }


def write(stories: list[dict], by_id: dict, topics: dict, date: str, model: str,
          facts: dict[str, dict] | None = None) -> tuple[dict, dict]:
    facts = facts or {}
    blocks = []
    for n, st in enumerate(stories, 1):
        parts = [f"### Storia {n} — sezione `{st['section']}`, sottosezione proposta "
                 f"`{st['subsection']}`, priorità {st['priority']}"]
        for iid in st["item_ids"]:
            it = by_id[iid]
            limit = TRANSCRIPT_CHARS if it["kind"] in ("video", "short") else CONTENT_CHARS
            meta = _meta_line(it)
            verified = f"\n{_facts_line(facts[it['url']])}" if it["url"] in facts else ""
            parts.append(f"FONTE: {it['label']} · {it['kind']} · official={it['official']} · "
                         f"autore={publisher(it)} · "
                         f"{(it['published'] or '')[:10]}{' · ' + meta if meta else ''}{verified}\n"
                         f"TITOLO: {it['title']}\nCONTENUTO: {(it['content'] or it['summary'])[:limit]}")
        blocks.append("\n\n".join(parts))
    prompt = _fill((PROMPTS_DIR / "digest.md").read_text(encoding="utf-8"),
                   DATE=date, PROFILE=topics["profile"].strip(), STORIES="\n\n---\n\n".join(blocks))
    return run_claude(prompt, write_schema(len(stories)), system=SYSTEM, model=model)


def written_problems(written: dict, n_stories: int) -> list[str]:
    """Controllo di qualità sulla scrittura: testi veri per (quasi) tutte le storie selezionate."""
    problems = []
    good = [w for w in written.get("stories", [])
            if 1 <= w.get("story", 0) <= n_stories and len(w.get("title", "")) >= 12
            and len(w.get("summary", "")) >= 40 and len(w.get("why", "")) >= 15]
    covered = len({w["story"] for w in good})
    if covered < max(1, round(n_stories * 0.8)):
        problems.append(f"scritte {covered} storie su {n_stories}")
    text = " ".join([*written.get("in_breve", []), *(w.get("title", "") + w.get("summary", "") for w in good)])
    if any(x in text.lower() for x in ("placeholder", "lorem ipsum", "todo")):
        problems.append("testo segnaposto nella risposta")
    if n_stories and not [x for x in written.get("in_breve", []) if len(x) >= 20]:
        problems.append("'In breve' mancante")
    return problems


def write_checked(stories, by_id, topics, date, model, facts) -> tuple[dict, dict]:
    """Scrive e controlla; se la risposta è incompleta la rifà. Dopo 3 tentativi si ferma:
    un report vuoto o a metà non deve mai partire (il 15/11/2026 era successo)."""
    last = []
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        written, stats = write(stories, by_id, topics, date, model, facts)
        last = written_problems(written, len(stories))
        if not last:
            stats["attempts"] = attempt
            return written, stats
        print(f"Scrittura da rifare (tentativo {attempt}/{WRITE_ATTEMPTS}): {'; '.join(last)}")
    raise BuildError("scrittura del report non riuscita: " + "; ".join(last))


# ---------- 3. controlli ----------

def fix_badge(badge: str, sources: list[dict]) -> str:
    """Il badge deve essere coerente con le fonti reali, qualunque cosa abbia scritto Claude."""
    official = any(s["official"] for s in sources)
    independent = len({publisher(s) for s in sources})
    if badge == "smentita":
        return badge if official else "da_verificare"   # per smentire serve una fonte ufficiale
    if official:
        # il redattore può dire che la fonte ufficiale NON conferma l'affermazione: resta il dubbio
        return "da_verificare" if badge == "da_verificare" else "ufficiale"
    if all(s["kind"] == "repo" for s in sources):
        return "dal_repo"   # descrizione del progetto stesso: affidabile su cosa fa, non ancora provato
    return "confermata" if independent >= 2 else "da_verificare"


async def check_links(urls: list[str]) -> dict[str, str]:
    """url → 'ok' | 'non_verificabile' | 'rotto'."""
    async def one(client, url):
        if any(h in url for h in UNVERIFIABLE_HOSTS):
            return url, "non_verificabile"
        try:
            r = await client.get(url)
            return url, "ok" if r.status_code < 400 else "rotto"
        except httpx.HTTPError:
            return url, "rotto"

    async with make_client() as client:
        return dict(await asyncio.gather(*(one(client, u) for u in dict.fromkeys(urls))))


def _subsection(section: str, written: str, proposed: str, topics: dict) -> str:
    """Solo id validi: per i creator il nome del creator, per le sezioni senza sottosezioni niente."""
    if section == "creators":
        return written or proposed
    allowed = next((s.get("subsections") or {} for s in topics["sections"] if s["id"] == section), {})
    for candidate in (written, proposed):
        if candidate in allowed:
            return candidate
    return ""


# ---------- orchestrazione ----------

def latest_raw() -> Path:
    files = sorted(RAW_DIR.glob("items-*.json"))
    if not files:
        raise FileNotFoundError("nessuna raccolta in data/raw: esegui prima `digest collect`")
    return files[-1]


def build(input_path: Path | None = None, model: str | None = None) -> tuple[Path, dict]:
    topics = _topics()
    model = model or topics["report"]["model"]
    raw_path = input_path or latest_raw()
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    items = raw["items"]
    prepare(items)
    by_id = {it["id"]: it for it in items}
    date = raw["generated_at"][:10]

    stories, triage_stats = triage(items, topics, date, model) if items else ([], {})
    if not stories and len(items) >= 12:   # zero storie con tanto materiale: probabile risposta a vuoto
        print("Selezione vuota con molto materiale: la rifaccio una volta")
        stories, triage_stats = triage(items, topics, date, model)
    facts = asyncio.run(repo_facts([by_id[i]["url"] for st in stories for i in st["item_ids"]]))
    # repo archiviate: non si propongono come novità
    for st in stories:
        st["item_ids"] = [i for i in st["item_ids"] if not facts.get(by_id[i]["url"], {}).get("archived")]
    stories = [st for st in stories if st["item_ids"]]
    written, write_stats = (write_checked(stories, by_id, topics, date, model, facts)
                            if stories else ({"in_breve": [], "stories": []}, {}))

    # fonti reali per ogni storia (prima le ufficiali, senza link doppi), poi verifica dei link
    for st in stories:
        srcs, urls = [], set()
        for i in st["item_ids"]:
            if by_id[i]["url"] not in urls:
                urls.add(by_id[i]["url"])
                srcs.append(by_id[i])
        srcs.sort(key=lambda s: not s["official"])
        st["sources"] = [{"name": s["label"], "title": s["title"], "url": s["url"],
                          "official": s["official"], "kind": s["kind"], "item_id": s["id"],
                          "meta": {**{k: v for k, v in (s.get("meta") or {}).items()
                                      if k in ("creator", "stars", "points", "comments", "duration")},
                                   **({"stars": facts[s["url"]]["stars"], "stars_verified": True,
                                       "license": facts[s["url"]]["license"]} if s["url"] in facts else {})}}
                         for s in srcs]
    links = asyncio.run(check_links([s["url"] for st in stories for s in st["sources"]]))

    texts = {w["story"]: w for w in written["stories"]}
    sections = {s["id"]: {"id": s["id"], "title": s["title"], "items": []} for s in topics["sections"]}
    sub_labels = {k: v for s in topics["sections"] for k, v in (s.get("subsections") or {}).items()}
    dropped_links = []
    for n, st in enumerate(stories, 1):
        w = texts.get(n)
        if not w:
            continue
        for s in st["sources"]:
            s["link"] = links.get(s["url"], "rotto")
        usable = [s for s in st["sources"] if s["link"] != "rotto"]
        if not usable:
            dropped_links.append(w["title"])
            continue
        sub = _subsection(st["section"], w["subsection"], st["subsection"], topics)
        sections[st["section"]]["items"].append({
            "id": f"{date}-{n:02d}",
            "subsection": sub,
            "subsection_label": sub_labels.get(sub, sub),
            "title": w["title"], "summary": w["summary"],
            "key_points": [p for p in w.get("key_points", []) if p.strip()][:4],
            "why": w["why"],
            "badge": fix_badge(w["badge"], usable), "badge_note": w["badge_note"],
            "importance": w["importance"],
            **({"short_hook": w["short_hook"].strip()}
               if st["section"] == "virali" and (w.get("short_hook") or "").strip() else {}),
            "primary_url": usable[0]["url"],
            "sources": usable,
        })
    for sec in sections.values():
        sec["items"].sort(key=lambda i: i["importance"])

    from digest.picks import choose_picks
    picks, picks_stats = choose_picks(list(sections.values()), topics, model)

    all_items = [i for sec in sections.values() for i in sec["items"]]
    badges: dict[str, int] = {}
    for i in all_items:
        badges[i["badge"]] = badges.get(i["badge"], 0) + 1
    words = sum(len(" ".join([i["title"], i["summary"], i["why"], *i["key_points"]]).split())
                for i in all_items)
    report = {
        "title": topics["report"]["title"],
        "date": date,
        "generated_at": datetime.now(UTC).isoformat(),
        "reading_minutes": max(1, round(words / 200)),
        "in_breve": written["in_breve"][:3],
        "picks": picks,
        "sections": list(sections.values()),
        "stats": {
            "collected": len(items),
            "stories": sum(len(s["items"]) for s in sections.values()),
            "discarded": len(items) - sum(len(st["item_ids"]) for st in stories),
            "dropped_broken_links": dropped_links,
            "source_errors": [s for s in raw.get("stats", []) if s.get("error")],
            "window_hours": raw.get("lookback_hours"),
            "model": model,
            "checks": {"links_tested": len(links), "links_ok": sum(v == "ok" for v in links.values()),
                       "links_unverifiable": sum(v == "non_verificabile" for v in links.values()),
                       "repos_verified": len(facts), "badges": badges,
                       "write_attempts": write_stats.get("attempts", 0)},
            "claude": {"selezione": triage_stats, "scrittura": write_stats, "scelte": picks_stats},
        },
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{date}.json"
    out.write_text(to_json(report), encoding="utf-8")
    (REPORTS_DIR / f"{date}.md").write_text(to_markdown(report), encoding="utf-8")
    write_html(out)
    return out, report


def write_html(json_path: Path) -> Path:
    from digest.render import to_html

    report = json.loads(json_path.read_text(encoding="utf-8"))
    html_path = json_path.with_suffix(".html")
    html_path.write_text(to_html(report), encoding="utf-8")
    return html_path


BADGE_LABEL = {"ufficiale": "✅ Ufficiale", "confermata": "🔁 Confermata",
               "da_verificare": "⚠️ Da verificare", "smentita": "❌ Smentita",
               "dal_repo": "📦 Dal progetto"}


def to_markdown(r: dict) -> str:
    """Anteprima leggibile del report (l'HTML vero arriva in Fase 3)."""
    out = [f"# {r['title']} — {r['date']}", "",
           f"*{r['stats']['stories']} notizie · circa {r['reading_minutes']} minuti di lettura · "
           f"{r['stats']['collected']} elementi raccolti, {r['stats']['discarded']} scartati come rumore*", ""]
    if r["in_breve"]:
        out += ["## In breve", ""] + [f"- {x}" for x in r["in_breve"]] + [""]
    titles = {i["id"]: i["title"] for sec in r["sections"] for i in sec["items"]}
    for key, label in (("linkedin", "Post LinkedIn del giorno"), ("short", "Short del giorno")):
        pk = (r.get("picks") or {}).get(key)
        if pk:
            out += [f"## {label}", "", f"**{titles.get(pk['item_id'], '')}**", "",
                    f"«{pk['hook']}»", "", pk["why"], ""]
    for sec in r["sections"]:
        out += [f"## {sec['title']}", ""]
        if not sec["items"]:
            out += ["Nessuna novità rilevante.", ""]
        for it in sec["items"]:
            tag = f"{it['subsection_label']} · " if it["subsection_label"] else ""
            out += [f"### {it['title']}",
                    f"*{tag}{BADGE_LABEL[it['badge']]}* — {it['badge_note']}", "",
                    it["summary"], "", *[f"- {p}" for p in it.get("key_points", [])],
                    "", f"**Perché ti serve:** {it['why']}", "",
                    *([f"**🎬 Idea Short:** {it['short_hook']}", ""] if it.get("short_hook") else []),
                    "Fonti: " + " · ".join(f"[{s['name']}]({s['url']})" for s in it["sources"]), ""]
    return "\n".join(out)

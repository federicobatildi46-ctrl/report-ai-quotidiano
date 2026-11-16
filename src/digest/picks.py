"""Le scelte del giorno: tra le notizie del report, quale conviene trasformare in post LinkedIn
(per la nicchia definita in topics.yaml → audience.linkedin) e quale in YouTube Short.

Una chiamata a Claude sui testi già scritti e verificati; il codice controlla che gli id esistano.
Non blocca mai il report: se qualcosa va storto, semplicemente non ci sono scelte.
"""

from digest import PROMPTS_DIR
from digest.claude import run_claude

BADGE_TEXT = {"ufficiale": "UFFICIALE", "confermata": "CONFERMATA (più fonti)",
              "da_verificare": "DA VERIFICARE (una sola fonte non ufficiale)",
              "smentita": "SMENTITA", "dal_repo": "DAL PROGETTO (non ancora provato)"}
MIN_SCORE = 6   # sotto questo voto è meglio non pubblicare niente che forzare una notizia debole

_PICK = {
    "type": "object",
    "properties": {
        "item_id": {"type": "string"},
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "hook": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["item_id", "score", "hook", "why"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "linkedin": {**_PICK, "properties": {
            **_PICK["properties"],
            "target": {"type": "string"}, "pain": {"type": "string"}, "angle": {"type": "string"},
            "caveat": {"type": "string"},
            "alternatives": {"type": "array", "items": {"type": "object", "properties": {
                "item_id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["item_id", "reason"]}},
        }, "required": [*_PICK["required"], "target", "pain", "angle", "caveat", "alternatives"]},
        "short": _PICK,
    },
    "required": ["linkedin", "short"],
}
SYSTEM = ("Sei il content strategist di Federico. Rispondi solo con dati conformi allo schema JSON. "
          "Usa solo gli id delle notizie che vedi e solo fatti presenti nei testi.")


def choose_picks(sections: list[dict], topics: dict, model: str) -> tuple[dict, dict]:
    items = {it["id"]: {**it, "section": sec["id"], "section_title": sec["title"]}
             for sec in sections for it in sec["items"]}
    if not items:
        return {}, {}
    audience = topics.get("audience") or {}
    lines = []
    for it in items.values():
        points = " | ".join(it.get("key_points") or [])
        lines.append(f"[{it['id']}] ({it['section_title']} · {BADGE_TEXT.get(it['badge'], it['badge'])})\n"
                     f"    {it['title']}\n    {it['summary']}\n"
                     + (f"    Punti: {points}\n" if points else "")
                     + f"    Perché serve a Federico: {it['why']}")
    prompt = ((PROMPTS_DIR / "picks.md").read_text(encoding="utf-8")
              .replace("{{PROFILE}}", topics["profile"].strip())
              .replace("{{AUDIENCE_LINKEDIN}}", (audience.get("linkedin") or "").strip())
              .replace("{{AUDIENCE_SHORTS}}", (audience.get("shorts") or "").strip())
              .replace("{{MIN_SCORE}}", str(MIN_SCORE))
              .replace("{{ITEMS}}", "\n".join(lines)))
    try:
        out, stats = run_claude(prompt, SCHEMA, system=SYSTEM, model=model, timeout=600)
    except Exception as e:   # le scelte sono un di più: mai bloccare il report
        print(f"Scelte del giorno non disponibili: {e}")
        return {}, {}

    picks = {}
    for key in ("linkedin", "short"):
        pk = out.get(key) or {}
        if pk.get("item_id") not in items or pk.get("score", 0) < MIN_SCORE or not pk.get("hook", "").strip():
            continue
        it = items[pk["item_id"]]
        pk = {**pk, "title": it["title"], "badge": it["badge"], "section": it["section"]}
        if key == "linkedin":
            pk["alternatives"] = [{**a, "title": items[a["item_id"]]["title"]}
                                  for a in pk.get("alternatives", [])
                                  if a.get("item_id") in items and a["item_id"] != pk["item_id"]][:2]
            if it["badge"] in ("da_verificare", "smentita") and not pk.get("caveat", "").strip():
                pk["caveat"] = "La notizia ha una sola fonte non ufficiale: verificala prima di pubblicare."
        picks[key] = pk
    return picks, stats

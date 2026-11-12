"""Fase 9 — il filtro impara dai voti 👍/👎 di Federico.

- data/feedback.json (versionato: lo legge anche il cloud): un voto per notizia, con sezione,
  fonti e motivo opzionale.
- prompt_block(): ultimi esempi votati + punteggio per fonte, da inserire nella selezione.
- distill(): Claude riassume tutti i voti in config/preferenze.md (regole leggibili e
  modificabili a mano), rigenerato in automatico ogni DISTILL_EVERY voti nuovi.
"""

import json
from collections import defaultdict
from datetime import UTC, datetime

from digest import CONFIG_DIR, DATA_DIR, PROMPTS_DIR, REPORTS_DIR
from digest.claude import run_claude

FEEDBACK_PATH = DATA_DIR / "feedback.json"            # lo scrive SOLO l'app sul PC
PREFS_STATE_PATH = DATA_DIR / "preferenze_stato.json"  # lo scrive chi rigenera le preferenze
PREFS_PATH = CONFIG_DIR / "preferenze.md"
REASONS = ["Rumore", "Già saputo", "Non mi serve", "Troppo tecnico"]
DISTILL_EVERY = 10
EXAMPLES = 25   # esempi recenti per segno da mostrare nella selezione


def _load() -> dict:
    if FEEDBACK_PATH.exists():
        return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    return {"votes": {}}


def _prefs_state() -> dict:
    if PREFS_STATE_PATH.exists():
        return json.loads(PREFS_STATE_PATH.read_text(encoding="utf-8"))
    return {"distilled_at_count": 0, "distilled_at": None}


def _save(data: dict) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def votes_for(date: str) -> dict[str, dict]:
    return {k: {"vote": v["vote"], "reason": v.get("reason")}
            for k, v in _load()["votes"].items() if v["date"] == date}


def vote(date: str, item_id: str, value: int, reason: str | None = None) -> dict:
    """value: 1 = 👍, -1 = 👎, 0 = togli il voto."""
    data = _load()
    if value == 0:
        data["votes"].pop(item_id, None)
        _save(data)
        return {"item_id": item_id, "vote": 0}
    report = json.loads((REPORTS_DIR / f"{date}.json").read_text(encoding="utf-8"))
    item, section = next(((it, s) for s in report["sections"] for it in s["items"] if it["id"] == item_id),
                         (None, None))
    if not item:
        raise KeyError(f"notizia {item_id} non trovata")
    data["votes"][item_id] = {
        "date": date, "vote": 1 if value > 0 else -1,
        "reason": reason if value < 0 and reason in REASONS else None,
        "title": item["title"], "section": section["id"], "subsection": item.get("subsection") or "",
        "sources": [s["name"] for s in item["sources"]],
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _save(data)
    return {"item_id": item_id, **data["votes"][item_id]}


def source_scores(votes: list[dict]) -> list[tuple[str, int, int]]:
    """(fonte, 👍, 👎) ordinate per numero di voti. Il nome include il creator (es. 'YouTube · Coco')."""
    score: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for v in votes:
        for s in set(v["sources"]):
            score[s][0 if v["vote"] > 0 else 1] += 1
    return sorted(((s, up, down) for s, (up, down) in score.items()), key=lambda x: -(x[1] + x[2]))


def prompt_block() -> str:
    """Testo per il prompt di selezione: cosa Federico ha apprezzato e scartato finora."""
    data = _load()
    votes = sorted(data["votes"].values(), key=lambda v: v["at"], reverse=True)
    parts = []
    if PREFS_PATH.exists():
        parts.append("### Le mie preferenze (riassunte dai miei voti)\n" + PREFS_PATH.read_text(encoding="utf-8").strip())
    if votes:
        ups = [v for v in votes if v["vote"] > 0][:EXAMPLES]
        downs = [v for v in votes if v["vote"] < 0][:EXAMPLES]
        if ups:
            parts.append("### Notizie che mi sono servite (👍)\n" + "\n".join(
                f"- [{v['section']}] {v['title']} — {', '.join(v['sources'][:2])}" for v in ups))
        if downs:
            parts.append("### Notizie che NON volevo (👎)\n" + "\n".join(
                f"- [{v['section']}] {v['title']} — {', '.join(v['sources'][:2])}"
                + (f" (motivo: {v['reason']})" if v.get("reason") else "") for v in downs))
        scores = [s for s in source_scores(votes) if s[1] + s[2] >= 3]
        if scores:
            parts.append("### Voti per fonte (👍/👎, almeno 3 voti)\n" + "\n".join(
                f"- {name}: {up}/{down}" for name, up, down in scores))
    if not parts:
        return "Nessun voto ancora: usa solo le regole sopra."
    return "\n\n".join(parts)


def needs_distill() -> bool:
    return len(_load()["votes"]) - _prefs_state()["distilled_at_count"] >= DISTILL_EVERY


def distill(model: str = "sonnet") -> str:
    """Riassume tutti i voti in regole leggibili (config/preferenze.md)."""
    data = _load()
    votes = sorted(data["votes"].values(), key=lambda v: v["at"])
    if not votes:
        raise ValueError("nessun voto da riassumere")
    lines = "\n".join(f"{'👍' if v['vote'] > 0 else '👎'} [{v['section']}/{v['subsection']}] {v['title']} "
                      f"— fonti: {', '.join(v['sources'])}" + (f" — motivo: {v['reason']}" if v.get("reason") else "")
                      for v in votes)
    current = PREFS_PATH.read_text(encoding="utf-8") if PREFS_PATH.exists() else "(nessuna)"
    prompt = ((PROMPTS_DIR / "preferences.md").read_text(encoding="utf-8")
              .replace("{{CURRENT}}", current).replace("{{VOTES}}", lines))
    schema = {"type": "object", "properties": {"markdown": {"type": "string"}}, "required": ["markdown"]}
    out, _ = run_claude(prompt, schema, model=model, timeout=600,
                        system="Analizzi preferenze editoriali. Rispondi solo con dati conformi allo schema JSON.")
    header = (f"<!-- Generato dai voti 👍/👎 il {datetime.now(UTC).date().isoformat()} "
              f"({len(votes)} voti). Puoi modificarlo a mano: la prossima rigenerazione terrà conto "
              f"delle tue modifiche. -->\n\n")
    PREFS_PATH.write_text(header + out["markdown"].strip() + "\n", encoding="utf-8")
    PREFS_STATE_PATH.write_text(json.dumps({"distilled_at_count": len(data["votes"]),
                                            "distilled_at": datetime.now(UTC).isoformat(timespec="seconds")},
                                           indent=1), encoding="utf-8")
    return PREFS_PATH.read_text(encoding="utf-8")

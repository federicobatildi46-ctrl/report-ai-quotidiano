"""Ponte con l'Analista Social (progetto accanto, ../Analista-social).

L'Analista scrive config/playbook_dati.md con cosa funziona nei MIEI post e in quelli dei
competitor (temi, hook, formati, CTA, esperimento in corso). Qui lo usiamo in tre punti:
  * scelta della notizia del giorno (prompts/picks.md → {{PLAYBOOK}})
  * scrittura del post (prompts/linkedin_post.md → {{PLAYBOOK}})
  * "Ottimizza con i dati": rilegge la bozza alla luce del playbook e propone una versione migliore

Il playbook è un di più: se manca o non si legge, tutto funziona come prima.
"""

import json
from datetime import UTC, datetime

from digest import CONFIG_DIR, PROMPTS_DIR
from digest.claude import run_claude

PLAYBOOK_PATH = CONFIG_DIR / "playbook_dati.md"
NO_PLAYBOOK = "(Playbook dei dati non disponibile: segui solo la guida della voce.)"


def playbook_block() -> str:
    try:
        text = PLAYBOOK_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return NO_PLAYBOOK
    return text or NO_PLAYBOOK


# Niente minItems/maxItems: con vincoli rigidi Claude rigenera (vedi CLAUDE.md).
SCHEMA = {
    "type": "object",
    "properties": {
        "punteggio": {"type": "integer", "minimum": 1, "maximum": 10,
                      "description": "Quanto la bozza segue il playbook dei dati, prima delle modifiche"},
        "giudizio": {"type": "string", "description": "1-2 frasi sul punto più forte e su quello più debole"},
        "variante_esperimento": {"type": "string", "description": "A, B o nessuna, per la versione ottimizzata"},
        "modifiche": {"type": "array", "items": {"type": "object", "properties": {
            "cosa": {"type": "string"}, "perche": {"type": "string"},
            "evidenza": {"type": "string", "description": "La riga del playbook (numeri, competitor) che la giustifica"},
        }, "required": ["cosa", "perche", "evidenza"]}},
        "versione_ottimizzata": {"type": "string", "description": "Il post completo, testo semplice senza markdown"},
        "hook_alternativi": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["punteggio", "giudizio", "variante_esperimento", "modifiche", "versione_ottimizzata",
                 "hook_alternativi"],
}
SYSTEM = ("Sei l'analista growth di Federico. Migliori i suoi post LinkedIn usando solo i dati del "
          "playbook e i fatti già presenti nella bozza. Rispondi solo con dati conformi allo schema JSON.")


def optimize(post_text: str, voice: str, audience: str, model: str) -> tuple[dict, dict]:
    prompt = ((PROMPTS_DIR / "optimize_post.md").read_text(encoding="utf-8")
              .replace("{{PLAYBOOK}}", playbook_block())
              .replace("{{VOICE}}", voice)
              .replace("{{AUDIENCE}}", audience)
              .replace("{{POST}}", post_text.strip()))
    out, stats = run_claude(prompt, SCHEMA, system=SYSTEM, model=model, timeout=600)
    out["creato"] = datetime.now(UTC).isoformat(timespec="seconds")
    out["playbook_del"] = playbook_date()
    return out, stats


def playbook_date() -> str:
    first = playbook_block().splitlines()[0] if PLAYBOOK_PATH.exists() else ""
    return first.split("al ", 1)[1].split(" ", 1)[0] if "aggiornato al " in first else ""


def save(path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

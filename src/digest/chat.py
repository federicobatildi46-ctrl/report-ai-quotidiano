"""Chat sotto la lezione: domande, chiarimenti e come applicarla al lavoro o a un cliente.

La conversazione è salvata accanto alla lezione (outputs/lezioni/<item_id>.chat.json, anche su
GitHub). Ogni risposta usa claude -p con: lezione completa, profilo, fonti, ultimi scambi.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from digest import CONFIG_DIR, PROMPTS_DIR
from digest.claude import run_claude
from digest.generate import output_path, read_output

HISTORY_TURNS = 8          # ultimi scambi passati a Claude (oltre resta salvato ma non inviato)
MAX_QUESTION = 2000


def chat_path(item_id: str) -> Path:
    return output_path("lezione", item_id).with_suffix(".chat.json")


def load(item_id: str) -> list[dict]:
    p = chat_path(item_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save(item_id: str, messages: list[dict]) -> Path:
    p = chat_path(item_id)
    p.write_text(json.dumps(messages, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def clear(item_id: str) -> None:
    p = chat_path(item_id)
    if p.exists():
        p.unlink()


def ask(item_id: str, question: str) -> dict:
    lesson_file = output_path("lezione", item_id)
    if not lesson_file.exists():
        raise FileNotFoundError("prima genera la lezione")
    question = question.strip()[:MAX_QUESTION]
    if not question:
        raise ValueError("domanda vuota")
    lesson = read_output(lesson_file)["markdown"]
    sources = re.search(r"## Fonti della notizia\s*\n(.*)", lesson, re.S)
    with open(CONFIG_DIR / "topics.yaml", encoding="utf-8") as f:
        topics = yaml.safe_load(f)

    messages = load(item_id)
    recent = messages[-HISTORY_TURNS * 2:]
    history = "\n\n".join(f"{'IO' if m['role'] == 'user' else 'TUTOR'}: {m['text']}" for m in recent) or "(inizio)"
    prompt = ((PROMPTS_DIR / "lesson_chat.md").read_text(encoding="utf-8")
              .replace("{{PROFILE}}", topics["profile"].strip())
              .replace("{{LESSON}}", lesson)
              .replace("{{SOURCES}}", sources.group(1).strip() if sources else "(vedi lezione)")
              .replace("{{HISTORY}}", history)
              .replace("{{QUESTION}}", question))
    model = (topics.get("generators") or {}).get("model", "sonnet")
    out, stats = run_claude(prompt, {"type": "object", "properties": {"answer": {"type": "string"}},
                                     "required": ["answer"]},
                            system="Sei un tutor pratico in italiano. Rispondi solo con dati conformi allo schema JSON.",
                            model=model, timeout=300)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    messages += [{"role": "user", "text": question, "at": now},
                 {"role": "assistant", "text": out["answer"].strip(), "at": now}]
    save(item_id, messages)
    return {"messages": messages, "secs": stats.get("secs")}

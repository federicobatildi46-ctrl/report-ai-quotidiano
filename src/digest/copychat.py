"""Chat "Potenzia il copy" nel pannello del post: Federico chiede (es. "hook più forte",
"più neuromarketing", "accorcia") e Claude risponde con una spiegazione breve e, quando serve,
la nuova versione completa del post. "Usa questa versione" la mette al posto del testo del post.

La conversazione è salvata accanto al post (outputs/linkedin/<id>.copy-chat.json, anche su GitHub)
e ogni richiesta lavora sull'ULTIMA versione proposta o sul testo attuale del post.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from digest import PROMPTS_DIR
from digest import generate as gen
from digest import playbook
from digest.claude import run_claude

HISTORY_TURNS = 6
MAX_REQUEST = 2000
MAX_POST_CHARS = 3000
SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "post": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["reply", "post", "changes"],
}
SYSTEM = ("Sei il copywriter LinkedIn di Federico, esperto di neuromarketing, in italiano. "
          "Rispondi solo con dati conformi allo schema JSON. Non inventare fatti.")


def chat_path(item_id: str) -> Path:
    return gen.output_path("post", item_id).with_suffix(".copy-chat.json")


def load(item_id: str) -> list[dict]:
    p = chat_path(item_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save(item_id: str, messages: list[dict]) -> Path:
    p = chat_path(item_id)
    p.write_text(json.dumps(messages, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def clear(item_id: str) -> None:
    chat_path(item_id).unlink(missing_ok=True)


def current_post(item_id: str) -> str:
    md = gen.read_output(gen.output_path("post", item_id))["markdown"]
    m = re.search(r"##\s*Post\s*\n(.*?)(?=\n##\s|\Z)", md, re.S)
    return (m.group(1) if m else md).strip()


def ask(item_id: str, request: str) -> dict:
    if not gen.output_path("post", item_id).exists():
        raise FileNotFoundError("prima genera il post")
    request = request.strip()[:MAX_REQUEST]
    if not request:
        raise ValueError("richiesta vuota")
    messages = load(item_id)
    # si lavora sull'ultima proposta non ancora applicata, altrimenti sul testo attuale del post
    last = next((m for m in reversed(messages) if m["role"] == "assistant" and m.get("post")), None)
    base = last["post"] if last and not last.get("applied") else current_post(item_id)
    history = "\n\n".join(
        f"{'FEDERICO' if m['role'] == 'user' else 'COPYWRITER'}: {m['text']}"
        for m in messages[-HISTORY_TURNS * 2:]) or "(inizio)"
    topics = gen._topics()
    voice = gen.VOICE_PATH.read_text(encoding="utf-8") if gen.VOICE_PATH.exists() else gen.NO_VOICE
    prompt = ((PROMPTS_DIR / "copy_chat.md").read_text(encoding="utf-8")
              .replace("{{VOICE}}", voice)
              .replace("{{AUDIENCE}}", ((topics.get("audience") or {}).get("linkedin") or "").strip())
              .replace("{{PLAYBOOK}}", playbook.playbook_block())
              .replace("{{POST}}", base)
              .replace("{{HISTORY}}", history)
              .replace("{{REQUEST}}", request))
    model = (topics.get("generators") or {}).get("model", "sonnet")
    out, stats = run_claude(prompt, SCHEMA, system=SYSTEM, model=model, timeout=400)

    post = (out.get("post") or "").strip()
    if post and post == base.strip():
        post = ""   # nessuna modifica reale: niente pulsante "usa questa versione"
    now = datetime.now(UTC).isoformat(timespec="seconds")
    messages += [{"role": "user", "text": request, "at": now},
                 {"role": "assistant", "text": out["reply"].strip(), "post": post,
                  "changes": [c for c in out.get("changes", []) if c.strip()][:6],
                  "chars": len(post), "too_long": len(post) > MAX_POST_CHARS, "at": now}]
    save(item_id, messages)
    return {"messages": messages, "secs": stats.get("secs")}


def apply(item_id: str, index: int) -> tuple[list[dict], Path]:
    """Mette la versione proposta nel messaggio `index` al posto del testo del post."""
    messages = load(item_id)
    if not (0 <= index < len(messages)) or not messages[index].get("post"):
        raise ValueError("versione non trovata")
    path = gen.save_post_text(item_id, messages[index]["post"])
    for m in messages:
        m.pop("applied", None)
    messages[index]["applied"] = datetime.now(UTC).isoformat(timespec="seconds")
    save(item_id, messages)
    return messages, path

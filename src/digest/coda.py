"""Coda dei post LinkedIn programmati: outputs/linkedin/coda.json (versionata su GitHub).

Ogni voce conserva il TESTO ESATTO confermato da Federico al momento della programmazione:
viene pubblicato quello, anche se nel frattempo il file del post cambia.
Stati: programmato → pubblicato | errore | annullato.
"""

import json
import uuid
from datetime import UTC, datetime

from digest import OUTPUTS_DIR

CODA_PATH = OUTPUTS_DIR / "linkedin" / "coda.json"


def load() -> list[dict]:
    return json.loads(CODA_PATH.read_text(encoding="utf-8")) if CODA_PATH.exists() else []


def save(entries: list[dict]) -> None:
    CODA_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")


def add(item_id: str, title: str, text: str, image: str | None, publish_at: str,
        status: str = "programmato", result: dict | None = None) -> dict:
    when = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
    if status == "programmato" and when <= datetime.now(UTC):
        raise ValueError("l'orario di pubblicazione deve essere nel futuro")
    entry = {"id": uuid.uuid4().hex[:8], "item_id": item_id, "title": title, "text": text,
             "image": image, "publish_at": when.astimezone(UTC).isoformat(timespec="minutes"),
             "status": status, "created": datetime.now(UTC).isoformat(timespec="seconds"),
             **(result or {})}
    entries = load()
    entries.append(entry)
    save(entries)
    return entry


def cancel(entry_id: str) -> dict:
    entries = load()
    for e in entries:
        if e["id"] == entry_id:
            if e["status"] != "programmato":
                raise ValueError(f"non annullabile: stato '{e['status']}'")
            e["status"] = "annullato"
            save(entries)
            return e
    raise KeyError(entry_id)


def publish_due() -> list[dict]:
    """Pubblica le voci programmate già scadute. Ritorna le voci toccate."""
    from digest.linkedin_pub import image_path, publish

    entries = load()
    now = datetime.now(UTC)
    touched = []
    for e in entries:
        if e["status"] != "programmato" or datetime.fromisoformat(e["publish_at"]) > now:
            continue
        try:
            e.update(publish(e["text"], image_path(e.get("image")), alt_text=e.get("title", "")))
            e["status"] = "pubblicato"
        except Exception as ex:
            e.update(status="errore", error=f"{type(ex).__name__}: {ex}"[:400])
        touched.append(e)
    if touched:
        save(entries)
    return touched

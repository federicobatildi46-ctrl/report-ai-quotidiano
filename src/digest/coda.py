"""Coda dei post LinkedIn programmati: outputs/linkedin/coda.json (versionata su GitHub).

Ogni voce conserva il TESTO ESATTO confermato da Federico al momento della programmazione:
viene pubblicato quello, anche se nel frattempo il file del post cambia.
Stati: programmato → pubblicato | errore | annullato | scaduto.

Chi pubblica (in quest'ordine): l'app sul PC all'orario esatto; se il PC è spento, il cloud
(.github/workflows/publish.yml, svegliato da una routine Claude ogni 30 minuti) 2 minuti dopo.
Un post rimasto indietro di oltre MAX_LATE_HOURS non esce più ("scaduto"): meglio un avviso che
un post pubblicato a sorpresa ore dopo (o un doppione di uno pubblicato a mano).
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

from digest import OUTPUTS_DIR

CODA_PATH = OUTPUTS_DIR / "linkedin" / "coda.json"
MAX_LATE_HOURS = 3


def load() -> list[dict]:
    return json.loads(CODA_PATH.read_text(encoding="utf-8")) if CODA_PATH.exists() else []


def save(entries: list[dict]) -> None:
    CODA_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")


def add(item_id: str, title: str, text: str, image: str | None, publish_at: str,
        status: str = "programmato", result: dict | None = None, carousel: bool = False,
        document_title: str = "") -> dict:
    when = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
    if status == "programmato" and when <= datetime.now(UTC):
        raise ValueError("l'orario di pubblicazione deve essere nel futuro")
    entry = {"id": uuid.uuid4().hex[:8], "item_id": item_id, "title": title, "text": text,
             "image": None if carousel else image, "carousel": carousel, "document_title": document_title,
             "publish_at": when.astimezone(UTC).isoformat(timespec="minutes"),
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


def due_entries(grace_seconds: int = 0, entries: list[dict] | None = None) -> list[dict]:
    """Voci programmate il cui orario (+ margine) è passato."""
    now = datetime.now(UTC)
    return [e for e in (entries if entries is not None else load()) if e["status"] == "programmato"
            and datetime.fromisoformat(e["publish_at"]) + timedelta(seconds=grace_seconds) <= now]


def next_due(within_minutes: int) -> datetime | None:
    """Orario del primo post programmato entro i prossimi `within_minutes` (anche se già passato)."""
    limit = datetime.now(UTC) + timedelta(minutes=within_minutes)
    times = [datetime.fromisoformat(e["publish_at"]) for e in load() if e["status"] == "programmato"]
    times = [t for t in times if t <= limit]
    return min(times) if times else None


def publish_due(grace_seconds: int = 0) -> list[dict]:
    """Pubblica le voci programmate già scadute. Ritorna le voci toccate.
    `grace_seconds`: il cloud aspetta un paio di minuti in più, così se il PC è acceso pubblica
    lui e il cloud trova il post già fatto (niente doppioni)."""
    from digest.linkedin_pub import carousel_pdf, image_path, publish

    entries = load()
    now = datetime.now(UTC)
    touched = []
    for e in due_entries(grace_seconds, entries):
        if now - datetime.fromisoformat(e["publish_at"]) > timedelta(hours=MAX_LATE_HOURS):
            e.update(status="scaduto", error=f"non pubblicato: oltre {MAX_LATE_HOURS} ore di ritardo")
            touched.append(e)
            continue
        try:
            e.update(publish(e["text"], image_path(e.get("image")), alt_text=e.get("title", ""),
                             document=carousel_pdf(e["item_id"]) if e.get("carousel") else None,
                             document_title=e.get("document_title", "")))
            e["status"] = "pubblicato"
        except Exception as ex:
            e.update(status="errore", error=f"{type(ex).__name__}: {ex}"[:400])
        touched.append(e)
    if touched:
        save(entries)
    return touched

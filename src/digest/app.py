"""Fase 5 — app locale su http://localhost:8787: report, archivio e pulsanti di generazione.

Gira solo sul PC (127.0.0.1). All'avvio scarica da GitHub i report del cloud; ogni contenuto
generato viene salvato in outputs/ e caricato su GitHub.
"""

import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from digest import REPORTS_DIR, ROOT
from digest import coda, gitsync, images
from digest import generate as gen
from digest import linkedin_pub as li

WEB_DIR = ROOT / "web"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

executor = ThreadPoolExecutor(max_workers=2)
jobs: dict[str, dict] = {}
sync_state = {"status": "in corso", "detail": "", "at": None}


def _pull():
    ok, out = gitsync.pull()
    sync_state.update(status="ok" if ok else "errore", detail=out[-300:],
                      at=datetime.now(UTC).isoformat(timespec="seconds"))


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_pull, daemon=True).start()
    yield


app = FastAPI(title="Report AI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
images.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/immagini", StaticFiles(directory=images.IMAGES_DIR), name="immagini")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/reports")
def list_reports():
    out = []
    for p in sorted(REPORTS_DIR.glob("????-??-??.json"), reverse=True):
        r = json.loads(p.read_text(encoding="utf-8"))
        out.append({"date": r["date"], "stories": r["stats"]["stories"],
                    "minutes": r["reading_minutes"], "headline": (r["in_breve"] or [""])[0]})
    return out


@app.get("/api/reports/{date}")
def get_report(date: str):
    path = REPORTS_DIR / f"{date}.json"
    if not DATE_RE.match(date) or not path.exists():
        raise HTTPException(404, "report non trovato")
    report = json.loads(path.read_text(encoding="utf-8"))
    report["outputs"] = gen.existing_outputs(date)
    return report


@app.get("/api/sync")
def get_sync():
    return sync_state


@app.post("/api/sync")
def do_sync():
    _pull()
    return sync_state


class GenerateRequest(BaseModel):
    date: str
    item_id: str
    kind: str
    force: bool = False


def _run_job(job_id: str, req: GenerateRequest):
    job = jobs[job_id]
    try:
        path = gen.generate(req.date, req.item_id, req.kind)
        ok, detail = gitsync.commit_and_push(
            [str(path.relative_to(ROOT))],
            f"{gen.KINDS[req.kind]['label']}: {gen.read_output(path)['meta'].get('notizia', req.item_id)[:60]}")
        # "fatto" solo alla fine, così l'app mostra anche l'esito del salvataggio su GitHub
        job.update(status="fatto", path=str(path.relative_to(ROOT)),
                   git="salvato su GitHub" if ok else f"non salvato su GitHub: {detail[-200:]}")
    except Exception as e:
        job.update(status="errore", error=f"{type(e).__name__}: {e}"[:500])


@app.post("/api/generate")
def start_generate(req: GenerateRequest):
    if req.kind not in gen.KINDS or not DATE_RE.match(req.date):
        raise HTTPException(400, "richiesta non valida")
    path = gen.output_path(req.kind, req.item_id)
    if path.exists() and not req.force:
        return {"job_id": None, "status": "fatto", "path": str(path.relative_to(ROOT))}
    for jid, j in jobs.items():   # stesso contenuto già in preparazione: non duplicare
        if j["status"] == "in corso" and (j["item_id"], j["kind"]) == (req.item_id, req.kind):
            return {"job_id": jid, "status": "in corso"}
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "in corso", "item_id": req.item_id, "kind": req.kind,
                    "started": datetime.now(UTC).isoformat(timespec="seconds")}
    executor.submit(_run_job, job_id, req)
    return {"job_id": job_id, "status": "in corso"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "lavoro non trovato")
    return jobs[job_id]


ITEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}$")


def _image_list(item_id: str) -> list[str]:
    return [f"/immagini/{p.name}" for p in images.existing_images(item_id)]


def _run_images(job_id: str, item_id: str):
    job = jobs[job_id]
    try:
        paths = images.generate_images(item_id)
        rel = [str(p.relative_to(ROOT)) for p in paths] + [str((images.IMAGES_DIR / f"{item_id}.json").relative_to(ROOT))]
        ok, detail = gitsync.commit_and_push(rel, f"Immagini post: {item_id}")
        job.update(status="fatto", images=_image_list(item_id),
                   git="salvate su GitHub" if ok else f"non salvate su GitHub: {detail[-200:]}")
    except Exception as e:
        job.update(status="errore", error=f"{type(e).__name__}: {e}"[:500])


@app.get("/api/images/{item_id}")
def list_images(item_id: str):
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    return {"images": _image_list(item_id)}


@app.post("/api/images/{item_id}")
def start_images(item_id: str):
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    if not gen.output_path("post", item_id).exists():
        raise HTTPException(409, "prima genera il post")
    for jid, j in jobs.items():
        if j["status"] == "in corso" and (j["item_id"], j["kind"]) == (item_id, "immagini"):
            return {"job_id": jid, "status": "in corso"}
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "in corso", "item_id": item_id, "kind": "immagini",
                    "started": datetime.now(UTC).isoformat(timespec="seconds")}
    executor.submit(_run_images, job_id, item_id)
    return {"job_id": job_id, "status": "in corso"}


# ---------- LinkedIn (Fase 8) ----------

oauth_states: set[str] = set()
CODA_FILE = str(coda.CODA_PATH.relative_to(ROOT))


@app.get("/api/linkedin/status")
def linkedin_status():
    return li.status()


@app.get("/linkedin/login")
def linkedin_login():
    try:
        url, state = li.auth_url()
    except li.LinkedInError as e:
        raise HTTPException(400, str(e))
    oauth_states.add(state)
    return RedirectResponse(url)


@app.get("/linkedin/callback")
def linkedin_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error or state not in oauth_states:
        msg = error_description or error or "richiesta non riconosciuta (riprova da 'Collega LinkedIn')"
        return HTMLResponse(f"<p>Collegamento LinkedIn non riuscito: {msg}</p><p><a href='/'>Torna all'app</a></p>", 400)
    oauth_states.discard(state)
    try:
        li.exchange_code(code)
    except li.LinkedInError as e:
        return HTMLResponse(f"<p>{e}</p><p><a href='/'>Torna all'app</a></p>", 400)
    # copia il token nei Secrets di GitHub, per i post programmati nel cloud
    threading.Thread(target=li.sync_cloud_secrets, daemon=True).start()
    return RedirectResponse("/?linkedin=ok")


class PublishRequest(BaseModel):
    item_id: str
    title: str
    text: str
    image: str | None = None
    publish_at: str | None = None   # ISO; assente = pubblica adesso


def _run_publish(job_id: str, req: PublishRequest):
    job = jobs[job_id]
    try:
        result = li.publish(req.text, li.image_path(req.image), alt_text=req.title)
        coda.add(req.item_id, req.title, req.text, req.image, result["published_at"],
                 status="pubblicato", result=result)
        ok, _ = gitsync.commit_and_push([CODA_FILE], f"LinkedIn: pubblicato «{req.title[:50]}»")
        job.update(status="fatto", url=result["url"], git="salvato su GitHub" if ok else "non salvato su GitHub")
    except Exception as e:
        job.update(status="errore", error=f"{type(e).__name__}: {e}"[:500])


@app.post("/api/linkedin/publish")
def linkedin_publish(req: PublishRequest):
    """Pubblica ADESSO. L'app la chiama solo dopo la conferma esplicita nel dialogo."""
    if not ITEM_RE.match(req.item_id) or not req.text.strip():
        raise HTTPException(400, "richiesta non valida")
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "in corso", "item_id": req.item_id, "kind": "pubblicazione",
                    "started": datetime.now(UTC).isoformat(timespec="seconds")}
    executor.submit(_run_publish, job_id, req)
    return {"job_id": job_id, "status": "in corso"}


@app.get("/api/coda")
def get_coda():
    return sorted(coda.load(), key=lambda e: e["publish_at"], reverse=True)


@app.post("/api/coda")
def schedule_post(req: PublishRequest):
    if not ITEM_RE.match(req.item_id) or not req.text.strip() or not req.publish_at:
        raise HTTPException(400, "richiesta non valida")
    if req.image:
        li.image_path(req.image)   # l'immagine deve esistere (ed essere su GitHub per il cloud)
    try:
        entry = coda.add(req.item_id, req.title, req.text, req.image, req.publish_at)
    except ValueError as e:
        raise HTTPException(400, str(e))
    files = [CODA_FILE] + ([f"outputs/linkedin/immagini/{req.image}"] if req.image else [])
    ok, detail = gitsync.commit_and_push(files, f"LinkedIn: programmato «{req.title[:50]}»")
    return {**entry, "git": "salvato su GitHub" if ok else f"ATTENZIONE, non salvato su GitHub: {detail[-200:]}"}


@app.delete("/api/coda/{entry_id}")
def cancel_post(entry_id: str):
    try:
        entry = coda.cancel(entry_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    ok, _ = gitsync.commit_and_push([CODA_FILE], f"LinkedIn: annullato «{entry['title'][:50]}»")
    return {**entry, "git": "salvato su GitHub" if ok else "non salvato su GitHub"}


@app.get("/api/outputs/{kind}/{item_id}")
def get_output(kind: str, item_id: str):
    if kind not in gen.KINDS or not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    path = gen.output_path(kind, item_id)
    if not path.exists():
        raise HTTPException(404, "non ancora generato")
    return {**gen.read_output(path), "path": str(path.relative_to(ROOT))}

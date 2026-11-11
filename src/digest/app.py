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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from digest import REPORTS_DIR, ROOT
from digest import generate as gen
from digest import gitsync

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
        job.update(status="fatto", path=str(path.relative_to(ROOT)))
        ok, detail = gitsync.commit_and_push(
            [str(path.relative_to(ROOT))],
            f"{gen.KINDS[req.kind]['label']}: {gen.read_output(path)['meta'].get('notizia', req.item_id)[:60]}")
        job["git"] = "salvato su GitHub" if ok else f"non salvato su GitHub: {detail[-200:]}"
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


@app.get("/api/outputs/{kind}/{item_id}")
def get_output(kind: str, item_id: str):
    if kind not in gen.KINDS or not re.match(r"^\d{4}-\d{2}-\d{2}-\d{2}$", item_id):
        raise HTTPException(400, "richiesta non valida")
    path = gen.output_path(kind, item_id)
    if not path.exists():
        raise HTTPException(404, "non ancora generato")
    return {**gen.read_output(path), "path": str(path.relative_to(ROOT))}

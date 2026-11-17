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
from digest import carousel, chat, coda, feedback, gitsync, images
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
    # voti rimasti sul PC (es. app chiusa prima del salvataggio automatico): caricali ora
    if feedback.FEEDBACK_PATH.exists():
        gitsync.commit_and_push([str(feedback.FEEDBACK_PATH.relative_to(ROOT))], "Voti 👍/👎 sulle notizie")
    # se GitHub non ha ancora fatto partire il report di oggi, lo chiediamo noi
    if ok:
        sync_state["report_today"] = gitsync.ensure_today_report()


CHECK_EVERY = 600   # secondi: l'app resta accesa per giorni, quindi ricontrolla da sola


def _keep_in_sync():
    """Ogni 10 minuti: scarica i report nuovi e, se quello di oggi manca, lo chiede al cloud.
    È una delle sveglie del report (l'orologio interno di GitHub parte con ore di ritardo)."""
    import time
    while True:
        try:
            _pull()
        except Exception as e:   # un errore di rete non deve fermare il controllo
            sync_state.update(status="errore", detail=str(e)[-300:])
        time.sleep(CHECK_EVERY)


def _publish_loop():
    """Ogni 30 secondi: se un post programmato è arrivato all'orario, il PC lo pubblica subito.
    Prima scarica la coda da GitHub (il cloud potrebbe averlo già fatto), dopo la ricarica.
    A PC spento ci pensa il cloud (publish.yml), 2 minuti dopo l'orario."""
    import time
    while True:
        time.sleep(30)
        try:
            if not coda.due_entries() or not li.load_token():
                continue
            gitsync.pull()
            if not coda.due_entries():
                continue
            touched = coda.publish_due()
            if touched:
                rel = str(coda.CODA_PATH.relative_to(ROOT))
                names = ", ".join(f"{e['status']}: {e['title'][:40]}" for e in touched)
                gitsync.commit_and_push([rel], f"LinkedIn dal PC: {names}")
        except Exception as e:   # mai fermare il controllo
            sync_state["publish_error"] = str(e)[-300:]


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_keep_in_sync, daemon=True).start()
    threading.Thread(target=_publish_loop, daemon=True).start()
    yield


app = FastAPI(title="Report AI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/fonts", StaticFiles(directory=ROOT / "assets" / "fonts"), name="fonts")   # Anton e Inter, come nei caroselli
images.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/immagini", StaticFiles(directory=images.IMAGES_DIR), name="immagini")
carousel.CAROUSEL_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/caroselli", StaticFiles(directory=carousel.CAROUSEL_DIR), name="caroselli")


@app.get("/")
def index():
    # ?v=<ultima modifica>: dopo un aggiornamento il browser non usa mai CSS o JS vecchi
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.css", "app.js"):
        v = int((WEB_DIR / name).stat().st_mtime)
        html = html.replace(f"/static/{name}", f"/static/{name}?v={v}")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


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
    report["feedback"] = feedback.votes_for(date)
    return report


# ---------- voti 👍/👎 (Fase 9) ----------

_fb_timer: threading.Timer | None = None
FEEDBACK_FILE = str(feedback.FEEDBACK_PATH.relative_to(ROOT))


def _push_feedback():
    gitsync.commit_and_push([FEEDBACK_FILE], "Voti 👍/👎 sulle notizie")


class VoteRequest(BaseModel):
    date: str
    item_id: str
    vote: int            # 1, -1, 0 (togli)
    reason: str | None = None


@app.post("/api/feedback")
def post_vote(req: VoteRequest):
    global _fb_timer
    if not DATE_RE.match(req.date) or not ITEM_RE.match(req.item_id) or req.vote not in (-1, 0, 1):
        raise HTTPException(400, "richiesta non valida")
    try:
        result = feedback.vote(req.date, req.item_id, req.vote, req.reason)
    except KeyError as e:
        raise HTTPException(404, str(e))
    # i voti si salvano su GitHub tutti insieme, 30 secondi dopo l'ultimo click
    if _fb_timer:
        _fb_timer.cancel()
    _fb_timer = threading.Timer(30, _push_feedback)
    _fb_timer.daemon = True
    _fb_timer.start()
    return result


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


# ---------- carosello e modifica del post ----------

def _push_async(paths: list[str], message: str):
    threading.Thread(target=gitsync.commit_and_push, args=(paths, message), daemon=True).start()


def _carousel_view(item_id: str) -> dict:
    plan = carousel.load_plan(item_id)
    if not plan:
        return {"exists": False}
    d = carousel.CAROUSEL_DIR / item_id
    v = int((d / "carosello.pdf").stat().st_mtime) if (d / "carosello.pdf").exists() else 0
    slides = [f"/caroselli/{item_id}/{p.name}?v={v}" for p in sorted(d.glob("slide-*.jpg"),
                                                                      key=lambda p: int(p.stem.split("-")[1]))]
    return {"exists": True, "plan": {k: plan[k] for k in ("cover", "slides", "cta")},
            "slides": slides, "pdf": f"/caroselli/{item_id}/carosello.pdf?v={v}",
            "title": carousel.pdf_title(plan)}


def _run_carousel(job_id: str, item_id: str, mode: str):
    job = jobs[job_id]
    try:
        if mode == "nuovo":
            carousel.build_carousel(item_id)
        else:
            carousel.new_subject(item_id)
        ok, detail = gitsync.commit_and_push(carousel.carousel_files(item_id), f"Carosello: {item_id}")
        job.update(status="fatto", git="salvato su GitHub" if ok else f"non salvato su GitHub: {detail[-200:]}")
    except Exception as e:
        job.update(status="errore", error=f"{type(e).__name__}: {e}"[:500])


def _start_job(item_id: str, kind: str, target, *args) -> dict:
    for jid, j in jobs.items():
        if j["status"] == "in corso" and (j["item_id"], j["kind"]) == (item_id, kind):
            return {"job_id": jid, "status": "in corso"}
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "in corso", "item_id": item_id, "kind": kind,
                    "started": datetime.now(UTC).isoformat(timespec="seconds")}
    executor.submit(target, job_id, item_id, *args)
    return {"job_id": job_id, "status": "in corso"}


@app.get("/api/carousel/{item_id}")
def get_carousel(item_id: str):
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    return _carousel_view(item_id)


@app.post("/api/carousel/{item_id}")
def create_carousel(item_id: str, nuova_immagine: bool = False):
    """Genera il carosello (testi + immagine nuovi) o, con nuova_immagine, cambia solo l'immagine."""
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    if not gen.output_path("post", item_id).exists():
        raise HTTPException(409, "prima genera il post")
    mode = "immagine" if nuova_immagine else "nuovo"
    return _start_job(item_id, f"carosello-{mode}", _run_carousel, mode)


@app.put("/api/carousel/{item_id}")
def edit_carousel(item_id: str, edited: dict):
    """Testi delle slide modificati a mano: nuova impaginazione, stessa immagine (gratis)."""
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    try:
        carousel.update_texts(item_id, edited)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    _push_async(carousel.carousel_files(item_id), f"Carosello modificato: {item_id}")
    return _carousel_view(item_id)


class PostText(BaseModel):
    text: str


@app.put("/api/outputs/post/{item_id}")
def edit_post(item_id: str, body: PostText):
    if not ITEM_RE.match(item_id) or not body.text.strip():
        raise HTTPException(400, "richiesta non valida")
    if not gen.output_path("post", item_id).exists():
        raise HTTPException(404, "post non trovato")
    path = gen.save_post_text(item_id, body.text)
    _push_async([str(path.relative_to(ROOT))], f"Post modificato: {item_id}")
    return {**gen.read_output(path), "path": str(path.relative_to(ROOT))}


# ---------- chat sotto la lezione ----------

class ChatQuestion(BaseModel):
    message: str


@app.get("/api/chat/{item_id}")
def get_chat(item_id: str):
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    return {"messages": chat.load(item_id)}


@app.post("/api/chat/{item_id}")
def post_chat(item_id: str, body: ChatQuestion):
    """Una domanda sulla lezione: risponde Claude (10-30 secondi)."""
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    try:
        result = chat.ask(item_id, body.message)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))
    _push_async([str(chat.chat_path(item_id).relative_to(ROOT))], f"Chat lezione: {item_id}")
    return result


@app.delete("/api/chat/{item_id}")
def delete_chat(item_id: str):
    if not ITEM_RE.match(item_id):
        raise HTTPException(400, "richiesta non valida")
    path = str(chat.chat_path(item_id).relative_to(ROOT))
    tracked = chat.chat_path(item_id).exists()
    chat.clear(item_id)
    if tracked:
        _push_async([path], f"Chat lezione svuotata: {item_id}")
    return {"messages": []}


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
        if error == "unauthorized_scope_error":
            msg += (". Soluzione: su linkedin.com/developers → la tua app → scheda Products, aggiungi "
                    "'Sign In with LinkedIn using OpenID Connect' e 'Share on LinkedIn', poi riprova.")
        elif "redirect_uri" in (error_description or ""):
            msg += (". Soluzione: nella scheda Auth dell'app aggiungi esattamente "
                    f"{li.redirect_uri()} tra gli Authorized redirect URLs.")
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
    carousel: bool = False          # allega il carosello PDF (ha la precedenza sull'immagine)
    publish_at: str | None = None   # ISO; assente = pubblica adesso


def _doc_title(item_id: str) -> str:
    plan = carousel.load_plan(item_id)
    return carousel.pdf_title(plan) if plan else "Carosello"


def _run_publish(job_id: str, req: PublishRequest):
    job = jobs[job_id]
    try:
        doc = li.carousel_pdf(req.item_id) if req.carousel else None
        result = li.publish(req.text, None if doc else li.image_path(req.image), alt_text=req.title,
                            document=doc, document_title=_doc_title(req.item_id) if doc else "")
        coda.add(req.item_id, req.title, req.text, req.image, result["published_at"],
                 status="pubblicato", result=result, carousel=req.carousel,
                 document_title=_doc_title(req.item_id) if doc else "")
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
    try:
        if req.carousel:
            li.carousel_pdf(req.item_id)   # il PDF deve esistere (ed essere su GitHub per il cloud)
        elif req.image:
            li.image_path(req.image)
        entry = coda.add(req.item_id, req.title, req.text, req.image, req.publish_at,
                         carousel=req.carousel, document_title=_doc_title(req.item_id) if req.carousel else "")
    except (ValueError, li.LinkedInError) as e:
        raise HTTPException(400, str(e))
    if req.carousel:
        files = [CODA_FILE] + carousel.carousel_files(req.item_id)
    else:
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

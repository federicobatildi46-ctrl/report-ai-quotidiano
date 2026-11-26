"""Chat "Modifica il report": Federico scrive cosa vuole cambiare (una sezione, un pulsante, un
colore, un'opzione) e Claude Code lo fa davvero sul progetto, come in una sessione con Claude.

Giro completo, tutto dall'app:
  1. git pull, poi `claude -p` nella cartella del progetto, con strumenti per leggere e modificare
     i file (CLAUDE.md gli spiega il progetto). La conversazione continua (--resume): si possono
     chiedere aggiustamenti ("più grande", "no, mettilo sopra").
  2. Controlli automatici sui file cambiati (Python si compila e l'app si importa, JS valido,
     YAML/JSON leggibili). Se falliscono, Claude prova a correggere una volta; poi si annulla tutto.
  3. Commit + push su GitHub. "Annulla l'ultima modifica" = git revert + push.
  4. Se è cambiato codice Python, l'app si riavvia da sola (il guardiano la riaccende).

Limiti voluti: niente .env o token, niente commit/push fatti da Claude, niente pubblicazioni,
email o report lanciati da qui.
"""

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from digest import CONFIG_DIR, DATA_DIR, ROOT, gitsync
from digest.claude import claude_executable

STATE_PATH = DATA_DIR / "tmp" / "modifica-report.json"   # solo su questo PC (data/tmp è ignorata da Git)
GUARDIAN_LOCK = DATA_DIR / "tmp" / "guardiano.lock"
TIMEOUT = 20 * 60
MAX_REQUEST = 4000

ALLOWED_TOOLS = [
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(uv run python:*)", "Bash(node --check:*)", "Bash(git status:*)", "Bash(git diff:*)",
    "Bash(git log:*)", "Bash(ls:*)",
]
DISALLOWED_TOOLS = [
    "Read(./.env)", "Edit(./.env)", "Write(./.env)",
    "Read(./data/linkedin_token.json)", "Edit(./data/linkedin_token.json)",
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(git reset:*)", "Bash(git checkout:*)",
    "Bash(uv run digest:*)", "WebFetch", "WebSearch",
]
SYSTEM = """Stai lavorando sul progetto "Report AI" di Federico attraverso la chat "Modifica il report"
che lui usa dentro l'app (http://localhost:8787). Federico non è un programmatore: è come se
parlasse con te in una sessione di Claude Code, ma senza vedere il codice.

Come lavorare:
- Leggi CLAUDE.md e i file che servono, poi fai DAVVERO la modifica richiesta nei file.
- Modifiche minime e mirate. Mantieni lo stile grafico esistente (colori e font dei caroselli) e
  tutto in italiano per ciò che Federico legge.
- Non toccare .env, token, data/seen.json, reports/ e outputs/ salvo richiesta esplicita.
- Non pubblicare su LinkedIn, non inviare email, non lanciare raccolta o report, non installare
  pacchetti. Non fare commit né push: li fa l'app dopo i controlli.
- Dopo modifiche Python verifica con `uv run python -c "import digest.app, digest.build"`;
  dopo modifiche a web/app.js verifica con `node --check web/app.js`.
- Se la richiesta è ambigua o rischiosa (cancellare dati, cambiare l'orario del report, toccare la
  pubblicazione), NON modificare: fai una domanda breve per chiarire.
- Alla fine rispondi in italiano semplice, 2-6 righe: cosa hai cambiato e dove si vede nell'app.
  Niente codice nella risposta, niente gergo."""

_lock = threading.Lock()


# ---------- stato della conversazione ----------

def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"session_id": None, "messages": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def reset() -> dict:
    state = {"session_id": None, "messages": []}
    save_state(state)
    return state


def _add(state: dict, role: str, text: str, **extra) -> None:
    state["messages"].append({"role": role, "text": text,
                              "at": datetime.now(UTC).isoformat(timespec="seconds"), **extra})


# ---------- git ----------

def _git(*args: str, timeout: int = 60) -> tuple[bool, str]:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _status() -> dict[str, str]:
    """path → codice di stato git (solo file tracciabili; data/tmp è ignorata).
    Formato -z: niente virgolette né spazi tagliati (con .strip() si perdeva la prima lettera)."""
    r = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    files, parts, i = {}, r.stdout.split("\0"), 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":   # rinomina/copia: il percorso di origine è nel campo successivo
            i += 1
        files[path] = code
    return files


def _fingerprint(paths) -> dict[str, str]:
    """Contenuto dei file già modificati prima della richiesta: per capire se Claude li ha toccati."""
    out = {}
    for p in paths:
        try:
            out[p] = hashlib.sha1((ROOT / p).read_bytes()).hexdigest()
        except OSError:
            out[p] = ""
    return out


def _changed_since(before: dict[str, str], prints: dict[str, str] | None = None) -> list[str]:
    after = _status()
    changed = {p for p, code in after.items() if before.get(p) != code}
    # file già modificati prima: contano solo se Claude ne ha cambiato il contenuto
    for p, fp in (prints or {}).items():
        if p in after and _fingerprint([p])[p] != fp:
            changed.add(p)
    return sorted(changed)


def _revert_files(paths: list[str], before: dict[str, str]) -> None:
    for p in paths:
        if before.get(p):   # era già modificato prima: non lo tocchiamo
            continue
        if _status().get(p, "").startswith("??"):
            try:
                (ROOT / p).unlink()
            except OSError:
                pass
        else:
            _git("checkout", "--", p)


# ---------- controlli ----------

def check_files(paths: list[str]) -> list[str]:
    """Errori trovati nei file cambiati (lista vuota = tutto a posto)."""
    errors = []
    python_changed = False
    for rel in paths:
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            if p.suffix == ".py":
                python_changed = True
                py_compile.compile(str(p), doraise=True)
            elif p.suffix in (".yaml", ".yml"):
                yaml.safe_load(p.read_text(encoding="utf-8"))
            elif p.suffix == ".json":
                json.loads(p.read_text(encoding="utf-8"))
            elif p.suffix == ".js" and shutil.which("node"):
                r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=60)
                if r.returncode:
                    errors.append(f"{rel}: {r.stderr.strip()[-400:]}")
        except (py_compile.PyCompileError, yaml.YAMLError, ValueError) as e:
            errors.append(f"{rel}: {str(e)[-400:]}")
    if python_changed or any(p.endswith((".yaml", ".yml")) for p in paths):
        # l'app e il report del mattino devono ancora caricarsi
        r = subprocess.run([sys.executable, "-c", "import digest.app, digest.build, digest.cli, digest.render"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if r.returncode:
            errors.append("l'app non si carica più: " + r.stderr.strip()[-600:])
    return errors


# ---------- Claude Code ----------

def _describe(tool: str, inp: dict) -> str | None:
    """Una riga leggibile per ogni passo di Claude (mostrata in diretta nell'app)."""
    path = inp.get("file_path") or inp.get("path") or ""
    name = Path(path).name if path else ""
    return {
        "Read": f"Leggo {name}" if name else "Leggo un file",
        "Edit": f"Modifico {name}",
        "Write": f"Scrivo {name}",
        "Glob": "Cerco i file giusti",
        "Grep": f"Cerco «{str(inp.get('pattern', ''))[:40]}» nel progetto",
        "Bash": "Controllo che funzioni" if any(k in str(inp.get("command", "")) for k in ("import", "--check"))
                else "Controllo il progetto",
    }.get(tool)


def _run_claude(message: str, session_id: str | None, model: str, steps: list[str]) -> tuple[str, str | None]:
    cmd = [claude_executable(), "-p", "--model", model,
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits",
           "--append-system-prompt", SYSTEM,
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--allowedTools", *ALLOWED_TOOLS,
           "--disallowedTools", *DISALLOWED_TOOLS]
    if session_id:
        cmd += ["--resume", session_id]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
    proc.stdin.write(message)
    proc.stdin.close()
    result, new_session, deadline = "", session_id, time.time() + TIMEOUT
    for line in proc.stdout:
        if time.time() > deadline:
            proc.kill()
            raise TimeoutError("Claude ci sta mettendo troppo (oltre 20 minuti): annullato")
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        new_session = ev.get("session_id") or new_session
        if ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    d = _describe(block.get("name", ""), block.get("input") or {})
                    if d and (not steps or steps[-1] != d):
                        steps.append(d)
        elif ev.get("type") == "result":
            if ev.get("is_error"):
                raise RuntimeError(f"Claude non ha completato: {str(ev.get('result'))[:400]}")
            result = (ev.get("result") or "").strip()
    proc.wait(timeout=60)
    if not result:
        err = proc.stderr.read()[-400:] if proc.stderr else ""
        raise RuntimeError(f"nessuna risposta da Claude {err}".strip())
    return result, new_session


def _model() -> str:
    try:
        topics = yaml.safe_load((CONFIG_DIR / "topics.yaml").read_text(encoding="utf-8"))
        return ((topics.get("editor") or {}).get("model")
                or (topics.get("generators") or {}).get("model") or "sonnet")
    except (OSError, yaml.YAMLError):
        return "sonnet"


def guardian_running() -> bool:
    """Il guardiano tiene aperto in scrittura il suo lucchetto: se non si apre, è acceso."""
    if not GUARDIAN_LOCK.exists():
        return False
    try:
        with open(GUARDIAN_LOCK, "a"):
            return False
    except OSError:
        return True


# ---------- il giro completo ----------

def run(request: str, job: dict) -> None:
    """Eseguito in un thread dall'app. Aggiorna `job` (stato, passi, esito)."""
    request = request.strip()[:MAX_REQUEST]
    steps = job.setdefault("steps", [])
    if not _lock.acquire(blocking=False):
        job.update(status="errore", error="c'è già una modifica in corso: aspetta che finisca")
        return
    state = load_state()
    try:
        steps.append("Scarico l'ultima versione da GitHub")
        gitsync.pull()
        before = _status()
        prints = _fingerprint(before)
        _add(state, "user", request)
        save_state(state)
        model = _model()

        answer, state["session_id"] = _run_claude(request, state.get("session_id"), model, steps)
        changed = _changed_since(before, prints)
        errors = check_files(changed) if changed else []
        if errors:
            steps.append("Un controllo non è passato: chiedo a Claude di correggere")
            fix = ("I controlli automatici dell'app hanno trovato questi errori nei file che hai cambiato. "
                   "Correggili senza cambiare altro, poi rispondi in 1-2 righe:\n" + "\n".join(errors))
            answer2, state["session_id"] = _run_claude(fix, state["session_id"], model, steps)
            changed = _changed_since(before, prints)
            errors = check_files(changed) if changed else []
            if not errors:
                answer = f"{answer}\n\n{answer2}"
        if errors:
            _revert_files(changed, before)
            msg = ("Ho provato, ma la modifica rompeva l'app, quindi l'ho annullata: tutto è com'era prima.\n\n"
                   f"Errore: {errors[0][:300]}\n\nProva a chiederlo in un altro modo o più a piccoli passi.")
            _add(state, "assistant", msg, error=True)
            save_state(state)
            job.update(status="fatto", reply=msg, changed=[], reverted=True, messages=state["messages"])
            return

        commit, git_note, restart = None, "", False
        if changed:
            steps.append("Salvo su GitHub")
            title = request.splitlines()[0][:70]
            ok, detail = gitsync.commit_and_push(changed, f"Modifica dall'app: {title}")
            if ok:
                _, commit = _git("rev-parse", "--short", "HEAD")
                git_note = "salvato su GitHub"
            else:
                git_note = f"salvato sul PC, non su GitHub: {detail[-160:]}"
            restart = any(p.startswith("src/") and p.endswith(".py") for p in changed)

        _add(state, "assistant", answer, files=changed, commit=commit, git=git_note)
        save_state(state)
        job.update(status="fatto", reply=answer, changed=changed, commit=commit, git=git_note,
                   restart=restart and guardian_running(), restart_manual=restart and not guardian_running(),
                   messages=state["messages"])
    except Exception as e:
        _add(state, "assistant", f"Non sono riuscito a completare: {type(e).__name__}: {str(e)[:300]}", error=True)
        save_state(state)
        job.update(status="errore", error=f"{type(e).__name__}: {e}"[:500], messages=state["messages"])
    finally:
        _lock.release()


def undo_last() -> dict:
    """Annulla l'ultima modifica fatta dalla chat (git revert del suo commit) e la salva su GitHub."""
    state = load_state()
    last = next((m for m in reversed(state["messages"]) if m.get("commit") and not m.get("undone")), None)
    if not last:
        raise ValueError("nessuna modifica da annullare")
    with _lock:
        gitsync.pull()
        ok, out = _git("revert", "--no-edit", last["commit"])
        if not ok:
            _git("revert", "--abort")
            raise RuntimeError(f"non riesco ad annullare automaticamente: {out[-300:]}")
        ok, out = _git("push")
    last["undone"] = True
    files = last.get("files") or []
    _add(state, "assistant", "↩️ Ultima modifica annullata: il progetto è tornato com'era prima."
         + ("" if ok else " (salvato sul PC, non ancora su GitHub)"))
    save_state(state)
    restart = any(p.startswith("src/") and p.endswith(".py") for p in files)
    return {"messages": state["messages"], "restart": restart and guardian_running(),
            "restart_manual": restart and not guardian_running()}


def restart_app_soon(delay: float = 2.5) -> None:
    """Chiude l'app dopo aver risposto: il guardiano la riaccende con il codice nuovo (~20-30 s)."""
    threading.Timer(delay, lambda: os._exit(0)).start()

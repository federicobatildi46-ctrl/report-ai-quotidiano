"""Sincronizzazione con GitHub dall'app locale: pull dei report del cloud, push dei contenuti creati."""

import subprocess
import threading

from digest import ROOT

_lock = threading.Lock()


def _git(*args: str, timeout: int = 60) -> tuple[bool, str]:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def pull() -> tuple[bool, str]:
    """Scarica i report del cloud. --autostash protegge eventuali modifiche locali."""
    with _lock:
        return _git("pull", "--rebase", "--autostash")


WAKE_FROM_UTC = (4, 45)   # dalle 05:45 italiane d'inverno (06:45 d'estate) il PC può svegliare il cloud
MAX_WAKES_PER_DAY = 3
_wakes: dict[str, int] = {}


def ensure_today_report() -> str:
    """Se il report di oggi non c'è (e nessun tentativo è in corso), chiede a GitHub di farlo.
    Chiamata all'avvio dell'app e poi ogni 10 minuti. Ritorna uno stato leggibile per l'app."""
    import json as _json
    from datetime import UTC, datetime

    from digest import REPORTS_DIR

    now = datetime.now(UTC)
    today = now.date().isoformat()
    if (REPORTS_DIR / f"{today}.json").exists():
        return "presente"
    if (now.hour, now.minute) < WAKE_FROM_UTC:
        return "in attesa del cloud"
    if _wakes.get(today, 0) >= MAX_WAKES_PER_DAY:
        return "già richiesto più volte oggi: controlla GitHub Actions"
    try:
        r = subprocess.run(["gh", "run", "list", "--workflow", "daily.yml", "--created",
                            f">={today}", "--json", "status"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
        runs = _json.loads(r.stdout or "[]")
        if any(x["status"] != "completed" for x in runs):
            return "in preparazione nel cloud"
        r = subprocess.run(["gh", "workflow", "run", "daily.yml"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            _wakes[today] = _wakes.get(today, 0) + 1
            return "richiesto ora al cloud (arriva in ~5 minuti)"
        return "non richiedibile (gh non disponibile)"
    except (OSError, subprocess.SubprocessError, ValueError):
        return "non richiedibile (gh non disponibile)"


def commit_and_push(paths: list[str], message: str) -> tuple[bool, str]:
    """Salva su GitHub i file creati dall'app (lezioni, post, script)."""
    with _lock:
        ok, out = _git("add", *paths)
        if not ok:
            return ok, out
        ok, out = _git("commit", "-m", message, "--", *paths)
        if not ok:
            return ok, out
        ok, out = _git("pull", "--rebase", "--autostash")
        if not ok:
            return ok, out
        return _git("push")

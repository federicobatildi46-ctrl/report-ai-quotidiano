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


def ensure_today_report() -> str:
    """Se il report di oggi non c'è (e nessun tentativo è in corso), chiede a GitHub di farlo.
    Ritorna uno stato leggibile per l'app."""
    import json as _json
    from datetime import UTC, datetime

    from digest import REPORTS_DIR

    now = datetime.now(UTC)
    if (REPORTS_DIR / f"{now.date().isoformat()}.json").exists():
        return "presente"
    if now.hour < 6:   # i tentativi automatici partono dalle 04:23 UTC: diamogli tempo
        return "in attesa del cloud"
    try:
        r = subprocess.run(["gh", "run", "list", "--workflow", "daily.yml", "--created",
                            f">={now.date().isoformat()}", "--json", "status"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
        runs = _json.loads(r.stdout or "[]")
        if any(x["status"] != "completed" for x in runs):
            return "in preparazione nel cloud"
        r = subprocess.run(["gh", "workflow", "run", "daily.yml"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        return "richiesto ora al cloud (arriva in ~5 minuti)" if r.returncode == 0 else "non richiedibile (gh non disponibile)"
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

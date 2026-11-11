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

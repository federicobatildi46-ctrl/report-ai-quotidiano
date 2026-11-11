"""Memoria di cosa è già stato visto (data/seen.json, versionato su GitHub).

Regola: una fonte vista per la prima volta viene "fotografata" — tutto ciò che c'è viene segnato
come visto, e nel report entra solo ciò che ha una data recente. Dal giorno dopo, ogni elemento
nuovo è una novità.
"""

import json
from datetime import UTC, datetime, timedelta

from digest import DATA_DIR
from digest.models import short_hash

SEEN_PATH = DATA_DIR / "seen.json"
KEEP_DAYS = 365


class SeenState:
    def __init__(self, data: dict | None = None):
        self.data = data or {"version": 1, "sources": {}}

    @classmethod
    def load(cls) -> "SeenState":
        if SEEN_PATH.exists():
            return cls(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
        return cls()

    def _src(self, source_id: str) -> dict:
        return self.data["sources"].setdefault(source_id, {"initialized": None, "keys": {}})

    def is_initialized(self, source_id: str) -> bool:
        return bool(self.data["sources"].get(source_id, {}).get("initialized"))

    def has(self, source_id: str, key: str) -> bool:
        return short_hash(key) in self.data["sources"].get(source_id, {}).get("keys", {})

    def commit(self, source_id: str, keys: list[str]) -> None:
        src = self._src(source_id)
        today = datetime.now(UTC).date().isoformat()
        for k in keys:
            src["keys"].setdefault(short_hash(k), today)
        src["initialized"] = src["initialized"] or today

    def prune(self) -> None:
        cutoff = (datetime.now(UTC) - timedelta(days=KEEP_DAYS)).date().isoformat()
        for src in self.data["sources"].values():
            src["keys"] = {k: d for k, d in src["keys"].items() if d >= cutoff}

    def save(self) -> None:
        self.prune()
        SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        SEEN_PATH.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")

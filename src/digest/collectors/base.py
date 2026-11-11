"""Contesto condiviso da tutti i collector."""

import re
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from digest.models import Item
from digest.state import SeenState


@dataclass
class Ctx:
    client: httpx.AsyncClient
    src: dict                 # la voce di config/sources.yaml
    section: str
    since: datetime           # inizio della finestra (UTC)
    state: SeenState
    remembered: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.src["id"]

    @property
    def initialized(self) -> bool:
        return self.state.is_initialized(self.id)

    def is_new(self, key: str) -> bool:
        """True se la chiave non è mai stata vista; in ogni caso la ricorda."""
        if self.state.has(self.id, key) or key in self.remembered:
            return False
        self.remembered.append(key)
        return True

    def excluded(self, title: str) -> bool:
        """Filtro anti-rumore deterministico per titolo (exclude_title in sources.yaml)."""
        pattern = self.src.get("exclude_title")
        return bool(pattern and re.search(pattern, title or "", re.I))

    def item(self, **kw) -> Item:
        kw.setdefault("subsection", self.src.get("subsection"))
        kw.setdefault("official", bool(self.src.get("official")))
        return Item(source_id=self.id, source_name=self.src["name"], section=self.section, **kw)

    def cap(self, items: list[Item], default: int = 12) -> list[Item]:
        items.sort(key=lambda i: i.published or "", reverse=True)
        return items[: self.src.get("max_items", default)]

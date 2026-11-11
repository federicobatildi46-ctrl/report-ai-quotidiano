"""Il formato comune di ogni notizia raccolta, qualunque sia la fonte."""

import hashlib
from dataclasses import asdict, dataclass, field


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


@dataclass
class Item:
    source_id: str
    source_name: str
    section: str               # claude | higgsfield | elevenlabs | creators | github
    subsection: str | None     # es. code, chat, siti_seo… ("auto" = decide Claude)
    kind: str                  # article | release | changelog | video | short | post | repo | incident | commit
    title: str
    url: str
    published: str | None = None   # ISO 8601
    summary: str = ""              # breve, per l'anteprima
    content: str = ""              # testo completo (troncato) per riassunto e fact check
    official: bool = False
    meta: dict = field(default_factory=dict)
    key: str = ""                  # chiave di deduplica (default: url)

    @property
    def id(self) -> str:
        return short_hash(self.key or self.url)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

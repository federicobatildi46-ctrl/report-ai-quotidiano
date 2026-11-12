"""Lettura di config/sources.yaml."""

from collections.abc import Iterator

import yaml

from digest import CONFIG_DIR

SECTIONS = ("claude", "higgsfield", "elevenlabs", "creators", "github", "virali")
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


def load_config() -> dict:
    with open(CONFIG_DIR / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_sources(cfg: dict | None = None) -> Iterator[tuple[str, dict]]:
    cfg = cfg or load_config()
    for section in SECTIONS:
        for src in cfg.get(section) or []:
            yield section, src


def check_url(src: dict) -> str | None:
    """URL da interrogare per `check-sources` (None = non verificabile con un GET)."""
    match src["type"]:
        case "youtube":
            return YOUTUBE_FEED.format(src["channel_id"])
        case "github_search":
            return "https://api.github.com/search/repositories?q=topic:claude-code&per_page=1"
        case "linkedin" | "websearch":
            return None
        case _:
            return src["url"]

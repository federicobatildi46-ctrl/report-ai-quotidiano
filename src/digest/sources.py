"""Caricamento di config/sources.yaml in una lista piatta di endpoint da interrogare."""

from dataclasses import dataclass

import yaml

from digest import CONFIG_DIR

YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


@dataclass
class Endpoint:
    id: str
    name: str
    section: str
    type: str
    url: str


def load_config() -> dict:
    with open(CONFIG_DIR / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def endpoints() -> list[Endpoint]:
    cfg = load_config()
    out: list[Endpoint] = []

    for section in ("claude", "higgsfield", "elevenlabs", "github"):
        for s in cfg.get(section, []):
            if s["type"] == "github_api":
                url = "https://api.github.com/search/repositories?q=topic:claude-code&sort=updated"
            else:
                url = s["url"]
            out.append(Endpoint(s["id"], s["name"], section, s["type"], url))

    creators = cfg.get("creators", {})
    for c in creators.get("youtube", []):
        out.append(Endpoint(c["id"], f"YouTube — {c['name']}", "creators", "youtube",
                            YOUTUBE_FEED.format(c["channel_id"])))
    for c in creators.get("linkedin", []):
        out.append(Endpoint(c["id"], f"LinkedIn — {c['name']}", "creators", "apify", c["url"]))

    return out

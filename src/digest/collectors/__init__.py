"""Registro dei collector: tipo di fonte → funzione."""

from digest.collectors.feeds import collect_feed, collect_github_releases, collect_hackernews
from digest.collectors.github import collect_github_search, collect_github_trending
from digest.collectors.linkedin import collect_linkedin
from digest.collectors.pages import collect_sections, collect_sitemap
from digest.collectors.youtube import collect_youtube

COLLECTORS = {
    "rss": collect_feed,
    "atom": collect_feed,
    "github_releases": collect_github_releases,
    "sitemap": collect_sitemap,
    "sections": collect_sections,
    "youtube": collect_youtube,
    "linkedin": collect_linkedin,
    "github_search": collect_github_search,
    "github_trending": collect_github_trending,
    "hackernews": collect_hackernews,
}

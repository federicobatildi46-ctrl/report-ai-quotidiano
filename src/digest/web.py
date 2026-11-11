"""Utilità HTTP e HTML condivise: client, date, estrazione testo degli articoli."""

import email.utils
import json
import re
from datetime import UTC, date, datetime

import httpx
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
          "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
DATE_RE = re.compile(rf"\b({MONTHS})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
PRIVATE_USE = re.compile(r"[-]")


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
        follow_redirects=True,
        timeout=httpx.Timeout(45, connect=20),
        limits=httpx.Limits(max_connections=12),
    )


def clean(text: str) -> str:
    text = PRIVATE_USE.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value) -> date | datetime | None:
    """Accetta ISO, RFC 822, 'November 9, 2026', struct_time. Ritorna date o datetime (UTC)."""
    if value is None or value == "":
        return None
    if hasattr(value, "tm_year"):
        return datetime(*value[:6], tzinfo=UTC)
    s = str(value).strip()
    try:
        if len(s) == 10 and ISO_DATE_RE.fullmatch(s):
            return date.fromisoformat(s)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        pass
    return find_date(s)


def find_date(text: str) -> date | None:
    m = DATE_RE.search(text or "")
    if m:
        try:
            return datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
        except ValueError:
            return None
    m = ISO_DATE_RE.search(text or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def is_fresh(d: date | datetime | None, since: datetime) -> bool:
    """Le date senza ora valgono per tutto il giorno (così 'ieri' non viene perso)."""
    if d is None:
        return False
    if isinstance(d, datetime):
        return d >= since
    return d >= since.date()


def iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d else None


def html_to_text(html: str, limit: int = 6000) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return clean(soup.get_text(" "))[:limit]


def extract_article(html: str, limit: int = 6000) -> dict:
    """Titolo, descrizione, data di pubblicazione e testo principale di una pagina."""
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names):
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    published = meta("article:published_time", "og:published_time", "datePublished")
    if not published:
        for script in soup.find_all("script", type="application/ld+json"):
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', script.string or "")
            if m:
                published = m.group(1)
                break
    if not published:
        t = soup.find("time", attrs={"datetime": True})
        published = t["datetime"] if t else None

    title = meta("og:title", "twitter:title") or (soup.title.string if soup.title else "") or ""
    description = meta("og:description", "description", "twitter:description") or ""

    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "svg", "form"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = clean(main.get_text(" "))
    if not published:
        published = find_date(text[:3000])

    return {
        "title": clean(title),
        "description": clean(description),
        "published": parse_date(published) if isinstance(published, str) else published,
        "text": text[:limit],
    }


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)

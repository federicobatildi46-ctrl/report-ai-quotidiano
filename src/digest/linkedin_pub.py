"""Fase 8 — pubblicazione sul profilo LinkedIn personale con l'API ufficiale.

- Accesso OAuth 2.0 (prodotti "Sign In with LinkedIn using OpenID Connect" + "Share on LinkedIn",
  scope: openid profile w_member_social). Il token dura 60 giorni; poi si ricollega con un click.
- Pubblicazione: Images API (initializeUpload → PUT del file) + Posts API (/rest/posts).
- Il testo va nel "little text format": caratteri riservati con backslash, hashtag come template.

Il token sta in data/linkedin_token.json (mai su GitHub). Nel cloud arriva dai Secrets
LINKEDIN_ACCESS_TOKEN e LINKEDIN_PERSON_URN, aggiornati in automatico a ogni collegamento.
"""

import json
import os
import re
import secrets
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
import yaml

from digest import CONFIG_DIR, DATA_DIR, OUTPUTS_DIR

TOKEN_PATH = DATA_DIR / "linkedin_token.json"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API = "https://api.linkedin.com"
SCOPES = "openid profile w_member_social"
RESERVED = set("\\|{}@[]()<>#*_~")
HASHTAG_RE = re.compile(r"(?<![\w#])#([0-9A-Za-zÀ-ÖØ-öø-ÿ_]+)")


class LinkedInError(RuntimeError):
    pass


def api_version() -> str:
    with open(CONFIG_DIR / "topics.yaml", encoding="utf-8") as f:
        return str((yaml.safe_load(f).get("linkedin") or {}).get("api_version", "202610"))


def redirect_uri() -> str:
    return f"http://localhost:{os.getenv('DIGEST_PORT', '8787')}/linkedin/callback"


# ---------- testo ----------

def _escape(s: str) -> str:
    return "".join("\\" + c if c in RESERVED else c for c in s)


def to_little_text(text: str) -> str:
    """Testo normale → little text format di LinkedIn (hashtag veri, niente caratteri rotti)."""
    parts = HASHTAG_RE.split(text)
    return "".join(_escape(p) if i % 2 == 0 else "{hashtag|\\#|" + _escape(p) + "}"
                   for i, p in enumerate(parts))


def post_text(markdown: str) -> str:
    """La sezione '## Post' di un file generato: il testo da pubblicare."""
    m = re.search(r"##\s*Post\s*\n(.*?)(?=\n##\s|\Z)", markdown, re.S)
    return (m.group(1) if m else markdown).strip()


# ---------- accesso ----------

def auth_url() -> tuple[str, str]:
    client_id = os.getenv("LINKEDIN_CLIENT_ID", "").strip()
    if not client_id:
        raise LinkedInError("manca LINKEDIN_CLIENT_ID in .env")
    state = secrets.token_urlsafe(16)
    return f"{AUTH_URL}?" + urlencode({"response_type": "code", "client_id": client_id,
                                       "redirect_uri": redirect_uri(), "state": state,
                                       "scope": SCOPES}), state


def exchange_code(code: str) -> dict:
    r = httpx.post(TOKEN_URL, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": os.getenv("LINKEDIN_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET", "").strip()}, timeout=30)
    if r.status_code != 200:
        raise LinkedInError(f"scambio del codice rifiutato ({r.status_code}): {r.text[:200]}")
    tok = r.json()
    me = httpx.get(f"{API}/v2/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"},
                   timeout=30)
    if me.status_code != 200:
        raise LinkedInError(f"profilo non leggibile ({me.status_code}): {me.text[:200]}")
    info = me.json()
    data = {"access_token": tok["access_token"],
            "expires_at": (datetime.now(UTC) + timedelta(seconds=int(tok.get("expires_in", 5184000)))).isoformat(),
            "person_urn": f"urn:li:person:{info['sub']}",
            "name": info.get("name") or "",
            "connected_at": datetime.now(UTC).isoformat()}
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def load_token() -> dict | None:
    """Prima l'ambiente (cloud), poi il file locale."""
    if os.getenv("LINKEDIN_ACCESS_TOKEN") and os.getenv("LINKEDIN_PERSON_URN"):
        return {"access_token": os.environ["LINKEDIN_ACCESS_TOKEN"].strip(),
                "person_urn": os.environ["LINKEDIN_PERSON_URN"].strip(), "expires_at": None}
    if TOKEN_PATH.exists():
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    return None


def status() -> dict:
    tok = load_token() if TOKEN_PATH.exists() else None
    out = {"configured": bool(os.getenv("LINKEDIN_CLIENT_ID") and os.getenv("LINKEDIN_CLIENT_SECRET")),
           "connected": False}
    if tok:
        exp = datetime.fromisoformat(tok["expires_at"])
        days = (exp - datetime.now(UTC)).days
        out.update(connected=days >= 0, name=tok.get("name"), expires_at=tok["expires_at"],
                   days_left=days, secrets_synced=tok.get("secrets_synced"))
    return out


def sync_cloud_secrets() -> bool:
    """Copia token e URN nei Secrets del repo, per la pubblicazione programmata nel cloud."""
    tok = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    ok = True
    for name, value in (("LINKEDIN_ACCESS_TOKEN", tok["access_token"]),
                        ("LINKEDIN_PERSON_URN", tok["person_urn"])):
        r = subprocess.run(["gh", "secret", "set", name], input=value, text=True,
                           capture_output=True, cwd=DATA_DIR.parent)
        ok &= r.returncode == 0
    tok["secrets_synced"] = datetime.now(UTC).isoformat() if ok else None
    TOKEN_PATH.write_text(json.dumps(tok, indent=1), encoding="utf-8")
    return ok


# ---------- pubblicazione ----------

def _headers(tok: dict) -> dict:
    return {"Authorization": f"Bearer {tok['access_token']}", "LinkedIn-Version": api_version(),
            "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}


def _require_token() -> dict:
    tok = load_token()
    if not tok:
        raise LinkedInError("LinkedIn non collegato: nell'app premi 'Collega LinkedIn'")
    if tok.get("expires_at") and datetime.fromisoformat(tok["expires_at"]) < datetime.now(UTC):
        raise LinkedInError("collegamento LinkedIn scaduto (dura 60 giorni): ricollegalo dall'app")
    return tok


def init_image_upload(tok: dict) -> dict:
    r = httpx.post(f"{API}/rest/images?action=initializeUpload", headers=_headers(tok),
                   json={"initializeUploadRequest": {"owner": tok["person_urn"]}}, timeout=30)
    if r.status_code != 200:
        raise LinkedInError(f"preparazione immagine rifiutata ({r.status_code}): {r.text[:300]}")
    return r.json()["value"]


def upload_image(tok: dict, path: Path) -> str:
    v = init_image_upload(tok)
    r = httpx.put(v["uploadUrl"], content=path.read_bytes(),
                  headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=120)
    if r.status_code not in (200, 201):
        raise LinkedInError(f"caricamento immagine fallito ({r.status_code})")
    urn = v["image"]
    for _ in range(15):   # LinkedIn elabora l'immagine per qualche secondo
        g = httpx.get(f"{API}/rest/images/{quote(urn, safe='')}", headers=_headers(tok), timeout=30)
        if g.status_code == 200 and g.json().get("status") == "AVAILABLE":
            break
        time.sleep(2)
    return urn


def publish(text: str, image: Path | None = None, alt_text: str = "") -> dict:
    """Pubblica DAVVERO sul profilo. Chiamarla solo dopo la conferma esplicita di Federico."""
    tok = _require_token()
    body = {"author": tok["person_urn"], "commentary": to_little_text(text), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    if image:
        body["content"] = {"media": {"id": upload_image(tok, image), "altText": alt_text[:300]}}
    r = httpx.post(f"{API}/rest/posts", headers=_headers(tok), json=body, timeout=60)
    if r.status_code != 201:
        raise LinkedInError(f"pubblicazione rifiutata ({r.status_code}): {r.text[:300]}")
    urn = r.headers.get("x-restli-id", "")
    return {"post_urn": urn, "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn else None,
            "published_at": datetime.now(UTC).isoformat(timespec="seconds")}


def check() -> dict:
    """Verifica senza pubblicare: profilo leggibile e permesso di caricare immagini a tuo nome."""
    tok = _require_token()
    me = httpx.get(f"{API}/v2/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"},
                   timeout=30)
    if me.status_code != 200:
        raise LinkedInError(f"token non valido ({me.status_code})")
    init_image_upload(tok)   # prenota un caricamento senza usarlo: conferma URN e permessi
    return {"name": me.json().get("name"), "person_urn": tok["person_urn"], "api_version": api_version()}


def image_path(filename: str | None) -> Path | None:
    if not filename:
        return None
    p = OUTPUTS_DIR / "linkedin" / "immagini" / Path(filename).name
    if not p.exists():
        raise LinkedInError(f"immagine non trovata: {filename}")
    return p

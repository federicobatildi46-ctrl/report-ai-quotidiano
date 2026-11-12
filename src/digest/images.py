"""Fase 7 — immagini dei post con il Soul di Federico, via CLI Higgsfield (`hf`).

Legge la sezione "## Prompt immagine" del post, genera N varianti con Higgsfield Soul 2.0 e le
salva in JPEG (qualità alta, ~10 volte più leggero del PNG) in outputs/linkedin/immagini/.
Costo indicativo: 0,12 crediti a immagine.
"""

import io
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import yaml
from PIL import Image

from digest import CONFIG_DIR, OUTPUTS_DIR
from digest.generate import output_path

IMAGES_DIR = OUTPUTS_DIR / "linkedin" / "immagini"


class ImageError(RuntimeError):
    pass


def _cfg() -> dict:
    with open(CONFIG_DIR / "topics.yaml", encoding="utf-8") as f:
        return (yaml.safe_load(f).get("generators") or {}).get("images") or {}


def hf_executable() -> str:
    found = shutil.which("higgsfield") or shutil.which("hf")
    if not found:
        raise ImageError("CLI Higgsfield non trovato: installa con `npm i -g @higgsfield/cli` "
                         "e accedi con `higgsfield auth login`")
    p = Path(found)
    if p.suffix.lower() in (".cmd", ".ps1", ""):   # il wrapper npm: meglio l'eseguibile nativo
        native = p.parent / "node_modules" / "@higgsfield" / "cli" / "vendor" / "hf.exe"
        if native.exists():
            return str(native)
    return found


def image_prompt(item_id: str) -> str:
    post = output_path("post", item_id)
    if not post.exists():
        raise ImageError("prima genera il post: l'immagine usa il suo 'Prompt immagine'")
    m = re.search(r"##\s*Prompt immagine\s*\n(.*?)(?=\n##\s|\Z)", post.read_text(encoding="utf-8"), re.S)
    if not m or not m.group(1).strip():
        raise ImageError("il post non contiene la sezione 'Prompt immagine'")
    return m.group(1).strip()


def existing_images(item_id: str) -> list[Path]:
    return sorted(IMAGES_DIR.glob(f"{item_id}-*.jpg"))


def _one(prompt: str, cfg: dict, dest: Path) -> dict:
    cmd = [hf_executable(), "generate", "create", cfg.get("model", "text2image_soul_v2"),
           "--prompt", prompt, "--custom_reference_id", cfg["soul_id"],
           "--aspect_ratio", cfg.get("aspect_ratio", "3:4"), "--quality", cfg.get("quality", "2k"),
           "--wait", "--wait-timeout", "6m", "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=420)
    try:
        job = json.loads(r.stdout)[0]
    except (json.JSONDecodeError, IndexError, KeyError):
        raise ImageError(f"Higgsfield non ha risposto come previsto: {(r.stderr or r.stdout)[:300]}") from None
    if job.get("status") != "completed" or not job.get("result_url"):
        raise ImageError(f"generazione non completata (stato: {job.get('status')})")
    png = httpx.get(job["result_url"], timeout=120).content
    Image.open(io.BytesIO(png)).convert("RGB").save(dest, "JPEG", quality=90, optimize=True)
    return {"file": dest.name, "job_id": job["id"], "url": job["result_url"]}


def generate_images(item_id: str, variants: int | None = None) -> list[Path]:
    cfg = _cfg()
    if not cfg.get("soul_id"):
        raise ImageError("manca generators.images.soul_id in config/topics.yaml")
    prompt = image_prompt(item_id)
    n = variants or cfg.get("variants", 2)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    start = len(existing_images(item_id)) + 1
    dests = [IMAGES_DIR / f"{item_id}-{start + i}.jpg" for i in range(n)]
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(lambda d: _one(prompt, cfg, d), dests))
    # registro accanto alle immagini: prompt e link originali su Higgsfield
    log = IMAGES_DIR / f"{item_id}.json"
    history = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    history.append({"prompt": prompt, "soul": cfg.get("soul_name"), "images": results})
    log.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    return dests

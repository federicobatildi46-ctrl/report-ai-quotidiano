"""Caroselli LinkedIn (5 slide, 1080×1350) nello stile dei riferimenti Pinterest di Federico:
blu elettrico + grigio carta, titoli enormi condensati (Anton), accenti in corsivo (Great Vibes),
testi in Inter, soggetto fotografico in bianco e nero ritagliato, grana, barra in basso.

Metodo ibrido: Higgsfield genera il soggetto (sfondo trasparente), il testo lo impagina il codice
con font veri → niente refusi, niente lettere deformate.
"""

import json
import random
import subprocess
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from digest import OUTPUTS_DIR, PROMPTS_DIR, ROOT
from digest.claude import run_claude
from digest.generate import VOICE_PATH, output_path
from digest.images import hf_executable
from digest.linkedin_pub import post_text

W, H = 1080, 1350
M = 70                                  # margine laterale
BLUE = (30, 90, 240)
BLUE_LIGHT = (52, 108, 246)             # filigrana su blu
PAPER = (233, 233, 230)
PAPER_DARK = (214, 214, 210)            # filigrana su carta
INK = (17, 17, 17)
WHITE = (255, 255, 255)
YELLOW = (244, 226, 66)
FONTS = ROOT / "assets" / "fonts"
CAROUSEL_DIR = OUTPUTS_DIR / "linkedin" / "caroselli"
FOOTER_NAME = "Federico Batildi · Digital Consultant"
NAME = "FEDERICO BATILDI"
SUBJECT_MODEL = "gpt_image_2_6"
# Etichetta "immagine generata con AI": disattivata su scelta di Federico (i soggetti sono collage
# evidentemente artistici, non foto realistiche). Per riattivarla basta mettere un testo qui.
AI_LABEL = ""

# Direzioni visive nello stile dei riferimenti: una diversa a ogni carosello, così ogni post ha
# un soggetto nuovo (sempre collegato al tema del post).
# (famiglia, direzione): le famiglie usate negli ultimi caroselli vengono escluse.
STYLE_DIRECTIONS = [
    ("statua", "classical marble statue or bust (Greek/Roman) interacting with modern technology"),
    ("retro", "vintage retro technology object (1970s TV, rotary phone, typewriter, cassette, radio) "
              "repurposed as a metaphor"),
    ("mani", "human hands in close-up doing a symbolic gesture with an object (chess piece, key, "
             "puzzle, lever, magnifying glass)"),
    ("spazio", "astronaut or space-age figure in an unexpected everyday situation"),
    ("testa-oggetto", "surreal editorial collage of an anonymous person whose head is replaced by an object"),
    ("vintage-ufficio", "vintage 1950s-60s businessman or office worker in a surreal situation"),
    ("tech-3d", "futuristic 3D object or device (VR headset, robot hand, glowing chip) as a still life"),
    ("animale", "an animal (owl, fox, chameleon, octopus...) as a clever metaphor, photographed like a "
                "studio portrait with one symbolic prop"),
    ("oggetto-gigante", "an everyday object at monumental scale (giant paper plane, oversized key, "
                        "huge light bulb) with a tiny figure for scale"),
]


def _family(direction: str) -> str:
    return next((f for f, d in STYLE_DIRECTIONS if d == direction), "")


# ---------- font e testo ----------

def anton(size):
    return ImageFont.truetype(str(FONTS / "Anton-Regular.ttf"), size)


def script(size):
    return ImageFont.truetype(str(FONTS / "GreatVibes-Regular.ttf"), size)


def inter(size, weight=500):
    f = ImageFont.truetype(str(FONTS / "Inter[opsz,wght].ttf"), size)
    f.set_variation_by_axes([min(max(size, 14), 32), weight])
    return f


def text_w(font, text) -> int:
    b = font.getbbox(text)
    return b[2] - b[0]


def fit(make, text, max_w, start, minimum=20):
    size = start
    while size > minimum and text_w(make(size), text) > max_w:
        size -= 4
    return make(size)


def wrap(font, text, max_w) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if text_w(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def spaced(draw, xy, text, font, fill, tracking=3):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += text_w(font, ch) + tracking
    return x


# ---------- fondi e cornice ----------

def background(color) -> Image.Image:
    img = Image.new("RGB", (W, H), color)
    noise = Image.effect_noise((W, H), 48).convert("RGB")
    img = Image.blend(img, noise, 0.07 if color == BLUE else 0.10)   # grana / carta
    if color != BLUE:   # leggera vignettatura sulla carta
        vign = Image.new("L", (W, H), 0)
        ImageDraw.Draw(vign).ellipse((-200, -150, W + 200, H + 150), fill=255)
        vign = vign.filter(ImageFilter.GaussianBlur(160))
        img = Image.composite(img, ImageEnhance.Brightness(img).enhance(0.93), vign)
    return img


def header(img, on_blue: bool):
    d = ImageDraw.Draw(img)
    f = inter(24, 700)
    color = WHITE if on_blue else INK
    label = f"{NAME}  ·  AI"
    w = sum(text_w(f, c) + 3 for c in label)
    x0 = (W - w) // 2
    d.ellipse((x0 - 46, 46, x0 - 14, 78), outline=color, width=3)
    d.text((x0 - 38, 50), "F", font=inter(20, 800), fill=color)
    spaced(d, (x0, 50), label, f, color)


def footer(img, page: int, total: int, on_blue: bool, swipe: bool = False):
    d = ImageDraw.Draw(img)
    top = H - 108
    d.rounded_rectangle((M - 20, top, W - M + 20, top + 64), radius=32, fill=WHITE)
    f = inter(24, 600)
    d.text((M + 10, top + 18), FOOTER_NAME, font=f, fill=INK)
    right = f"{page}/{total}" + ("   SCORRI →" if swipe else "")
    d.text((W - M - 10 - text_w(f, right), top + 18), right, font=f, fill=BLUE)


def ai_label(img):
    """Indicazione discreta sopra la barra, in basso a destra (solo se AI_LABEL non è vuota)."""
    if not AI_LABEL:
        return img
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = inter(18, 500)
    d.text((W - M - text_w(f, AI_LABEL), H - 136), AI_LABEL, font=f, fill=(255, 255, 255, 170))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def watermark(img, text, color, y, size=420):
    d = ImageDraw.Draw(img)
    f = fit(anton, text, W + 300, size)
    d.text(((W - text_w(f, text)) // 2, y), text, font=f, fill=color)


# ---------- soggetto ----------

def subject_bw(path: Path) -> Image.Image:
    """Soggetto ritagliato in bianco e nero ad alto contrasto, con l'alfa originale."""
    src = Image.open(path).convert("RGBA")
    alpha = src.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        src, alpha = src.crop(bbox), alpha.crop(bbox)
    gray = ImageOps.autocontrast(ImageOps.grayscale(src.convert("RGB")), cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.25)
    out = Image.merge("RGBA", (gray, gray, gray, alpha))
    return out


def paste_with_shadow(base: Image.Image, fg: Image.Image, xy, shadow=40):
    x, y = xy
    sh = Image.new("RGBA", fg.size, (0, 0, 0, 0))
    sh.putalpha(fg.getchannel("A").point(lambda a: int(a * 0.45)))
    sh = sh.filter(ImageFilter.GaussianBlur(shadow // 2))
    base.paste(sh, (x + 18, y + 24), sh)
    base.paste(fg, (x, y), fg)


def generate_subject(prompt_en: str, dest: Path) -> dict:
    prompt = (f"{prompt_en}. Black and white editorial photograph, isolated subject cut out on a "
              "fully transparent background, studio lighting, high contrast, fine film grain, sharp "
              "details, vintage magazine collage aesthetic. No text, no letters, no numbers, no logos, "
              "no watermark, no background, no frame.")
    cmd = [hf_executable(), "generate", "create", SUBJECT_MODEL, "--prompt", prompt,
           "--background", "transparent", "--aspect_ratio", "3:4", "--quality", "high",
           "--resolution", "2k", "--output_format", "png", "--wait", "--wait-timeout", "8m", "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=560)
    job = json.loads(r.stdout)[0]
    if job.get("status") != "completed":
        raise RuntimeError(f"soggetto non generato: {job.get('status')}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(httpx.get(job["result_url"], timeout=120).content)
    return {"job_id": job["id"], "url": job["result_url"], "model": SUBJECT_MODEL, "prompt": prompt}


# ---------- slide ----------

def cover(plan: dict, subj: Image.Image, total: int) -> Image.Image:
    c = plan["cover"]
    img = background(BLUE).convert("RGBA")
    d = ImageDraw.Draw(img)
    header(img, True)
    # kicker
    spaced(d, (M, 150), c["kicker"].upper(), inter(30, 800), WHITE, tracking=4)
    # titolone (dietro al soggetto)
    big = fit(anton, c["title_big"].upper(), W - 2 * M, 380)
    d.text((M - 6, 175), c["title_big"].upper(), font=big, fill=WHITE)
    big_bottom = 175 + big.getbbox(c["title_big"].upper())[3]
    # soggetto grande in primo piano: copre la base del titolo ed esce dal bordo in basso
    top = big_bottom - 150
    s = subj.copy()
    s.thumbnail((int(W * 0.92), H + 60 - top), Image.LANCZOS)
    paste_with_shadow(img, s, (W - s.width + 40, H + 60 - s.height))
    d = ImageDraw.Draw(img)
    # resto del titolo (una riga, su fascia nera) + accento in corsivo, sopra al soggetto
    rest_text = c["title_rest"].upper()
    rest = fit(anton, rest_text, W - 2 * M, 84)
    y = big_bottom + 14
    d.rectangle((M - 10, y + 10, M + text_w(rest, rest_text) + 12, y + rest.size + 10), fill=INK)
    d.text((M, y - 4), rest_text, font=rest, fill=WHITE)
    y += rest.size + 26
    acc = script(118)
    layer = Image.new("RGBA", (text_w(acc, c["script_accent"]) + 60, 220), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20, 10), c["script_accent"], font=acc, fill=YELLOW)
    layer = layer.rotate(7, expand=True, resample=Image.BICUBIC)
    img.paste(layer, (M - 10, y + 10), layer)
    # barra di ricerca
    d = ImageDraw.Draw(img)
    q = c["search_bar"]
    f = fit(lambda s: inter(s, 700), q, 520, 30)
    bw = min(text_w(f, q) + 120, W - 2 * M)
    by = H - 220
    d.rounded_rectangle((M, by, M + bw, by + 74), radius=37, fill=WHITE)
    d.text((M + 30, by + 21), q, font=f, fill=BLUE)
    cx, cy = M + bw - 50, by + 34
    d.ellipse((cx - 14, cy - 14, cx + 10, cy + 10), outline=BLUE, width=5)
    d.line((cx + 8, cy + 8, cx + 20, cy + 20), fill=BLUE, width=6)
    footer(img, 1, total, True, swipe=True)
    return ai_label(img).convert("RGB")


PILL_COLORS = [YELLOW, (236, 92, 168), (64, 214, 140), WHITE]


def pills(d, tags, y, on_blue) -> int:
    """Etichette colorate a pillola (stile secondo riferimento). Ritorna la y sotto le pillole."""
    f = inter(30, 700)
    x = M
    for i, t in enumerate(tags[:3]):
        w = text_w(f, t) + 48
        if x + w > W - M:
            x, y = M, y + 72
        color = PILL_COLORS[i % len(PILL_COLORS)]
        if not on_blue and color == WHITE:
            color = INK
        d.rounded_rectangle((x, y, x + w, y + 58), radius=29, fill=color,
                            outline=INK if not on_blue else None, width=2)
        d.text((x + 24, y + 12), t, font=f, fill=WHITE if color == INK else INK)
        x += w + 16
    return y + 58


def content(slide: dict, n: int, total: int, on_blue: bool) -> Image.Image:
    img = background(BLUE if on_blue else PAPER)
    fg, accent = (WHITE, WHITE) if on_blue else (INK, BLUE)
    # numerone in filigrana, in basso a destra e tagliato dal bordo (non dietro al testo)
    d = ImageDraw.Draw(img)
    num = f"0{n - 1}"
    wf = anton(760)
    d.text((W - int(text_w(wf, num) * 0.55), H - 700), num, font=wf,
           fill=BLUE_LIGHT if on_blue else PAPER_DARK)
    header(img, on_blue)
    d = ImageDraw.Draw(img)

    # misura il blocco per centrarlo verticalmente tra intestazione e barra
    title = slide["title"].upper()
    tf = anton(150)
    tlines = wrap(tf, title, W - 2 * M)
    if len(tlines) > 2:
        tf = anton(120)
        tlines = wrap(tf, title, W - 2 * M)
    body = inter(46, 500)
    blines = [wrap(body, line, W - 2 * M - 64) for line in slide["lines"]]
    hf_ = inter(42, 800)
    hl = wrap(hf_, slide["highlight"], W - 2 * M - 60) if slide.get("highlight") else []
    tags = slide.get("tags") or []
    block = (50 + len(tlines) * (tf.size + 14) + 36 + sum(len(b) * 62 + 26 for b in blines)
             + (len(hl) * 56 + 36 + 40 if hl else 0) + (58 + 40 if tags else 0))
    y = max(140, 120 + (H - 260 - block) // 2)

    spaced(d, (M, y), num, inter(30, 800), accent, tracking=4)
    y += 50
    for line in tlines:
        d.text((M - 4, y), line, font=tf, fill=accent)
        y += tf.size + 14
    y += 36
    for parts in blines:
        for i, part in enumerate(parts):
            if i == 0:
                d.text((M, y), "→", font=inter(46, 700), fill=YELLOW if on_blue else BLUE)
            d.text((M + 64, y), part, font=body, fill=fg)
            y += 62
        y += 26
    if tags:
        y = pills(d, tags, y + 4, on_blue) + 40
    if hl:
        box_h = len(hl) * 56 + 36
        d.rectangle((M, y, W - M, y + box_h), fill=YELLOW)
        for i, part in enumerate(hl):
            d.text((M + 30, y + 18 + i * 56), part, font=hf_, fill=INK)
    footer(img, n, total, on_blue)
    return img


def cta(plan: dict, subj: Image.Image, total: int) -> Image.Image:
    c = plan["cta"]
    img = background(BLUE).convert("RGBA")
    s = subj.copy()
    s.thumbnail((int(W * 0.56), int(H * 0.52)), Image.LANCZOS)
    paste_with_shadow(img, s, (W - s.width + 30, H + 40 - s.height))
    header(img, True)
    d = ImageDraw.Draw(img)
    spaced(d, (M, 150), "PRIMA DI ANDARE", inter(28, 800), WHITE, tracking=4)
    tf = anton(130)
    y = 200
    for line in wrap(tf, c["title"].upper(), W - 2 * M):
        d.text((M - 4, y), line, font=tf, fill=WHITE)
        y += tf.size + 12
    y += 50
    tx = inter(42, 500)
    for part in wrap(tx, c["text"], W - 2 * M):
        d.text((M, y), part, font=tx, fill=WHITE)
        y += 58
    y += 34
    kw = f"Commenta «{c['keyword'].upper()}»"
    kf = inter(46, 800)
    d.rectangle((M, y, M + text_w(kf, kw) + 64, y + 90), fill=YELLOW)
    d.text((M + 32, y + 20), kw, font=kf, fill=INK)
    # blocco "seguimi" in basso a sinistra, accanto alla statua
    ff = inter(38, 800)
    btn = "+  Segui Federico"
    by = H - 380
    d.rounded_rectangle((M, by, M + text_w(ff, btn) + 76, by + 82), radius=41, fill=WHITE)
    d.text((M + 38, by + 20), btn, font=ff, fill=BLUE)
    fy = by + 108
    fl = inter(36, 600)
    for part in wrap(fl, "per non perderti nessun aggiornamento su AI e automazioni.", int(W * 0.5)):
        d.text((M, fy), part, font=fl, fill=WHITE)
        fy += 48
    footer(img, total, total, True)
    return ai_label(img).convert("RGB")


# ---------- orchestrazione ----------

SCHEMA = {
    "type": "object",
    "properties": {
        "cover": {"type": "object", "properties": {
            "kicker": {"type": "string"}, "title_big": {"type": "string"}, "title_rest": {"type": "string"},
            "script_accent": {"type": "string"}, "search_bar": {"type": "string"}, "subject_en": {"type": "string"}},
            "required": ["kicker", "title_big", "title_rest", "script_accent", "search_bar", "subject_en"]},
        "slides": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}},
            "highlight": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "lines"]}},
        "cta": {"type": "object", "properties": {
            "title": {"type": "string"}, "text": {"type": "string"}, "keyword": {"type": "string"}},
            "required": ["title", "text", "keyword"]},
    },
    "required": ["cover", "slides", "cta"],
}


def previous_subjects(exclude: str | None = None, limit: int = 15) -> list[dict]:
    """Soggetti e direzioni dei caroselli già fatti (per non ripetersi)."""
    out = []
    for p in sorted(CAROUSEL_DIR.glob("*/carosello.json"), reverse=True):
        if p.parent.name == exclude:
            continue
        plan = json.loads(p.read_text(encoding="utf-8"))
        out.append({"subject": plan["cover"].get("subject_en", ""), "direction": plan.get("direction", "")})
    return out[:limit]


def pick_direction(previous: list[dict]) -> str:
    """Una direzione di una famiglia non usata negli ultimi caroselli (anche se vecchi senza
    famiglia: si riconoscono le statue dal soggetto)."""
    recent = set()
    for p in previous[:len(STYLE_DIRECTIONS) - 3]:
        fam = _family(p.get("direction", ""))
        if not fam and any(w in p.get("subject", "").lower() for w in ("statue", "bust", "marble", "sculpture")):
            fam = "statua"
        recent.add(fam)
    choices = [d for f, d in STYLE_DIRECTIONS if f not in recent] or [d for _, d in STYLE_DIRECTIONS]
    return random.choice(choices)


def plan_carousel(item_id: str) -> dict:
    post = output_path("post", item_id)
    if not post.exists():
        raise FileNotFoundError("prima genera il post: il carosello parte dal suo testo")
    voice = VOICE_PATH.read_text(encoding="utf-8") if VOICE_PATH.exists() else ""
    previous = previous_subjects(exclude=item_id)
    direction = pick_direction(previous)
    avoid = "\n".join(f"- {p['subject']}" for p in previous if p["subject"]) or "- (nessuno)"
    prompt = ((PROMPTS_DIR / "carousel.md").read_text(encoding="utf-8")
              .replace("{{VOICE}}", voice).replace("{{POST}}", post_text(post.read_text(encoding="utf-8")))
              .replace("{{DIRECTION}}", direction).replace("{{AVOID}}", avoid))
    out, _ = run_claude(prompt, SCHEMA, model="sonnet", timeout=600,
                        system="Progetti caroselli LinkedIn in italiano. Rispondi solo con dati conformi allo schema JSON.")
    out["slides"] = out["slides"][:3]
    out["direction"] = direction
    return out


def render(plan: dict, subject_path: Path, out_dir: Path) -> list[Path]:
    subj = subject_bw(subject_path)
    total = 2 + len(plan["slides"])
    slides = [cover(plan, subj, total)]
    for i, s in enumerate(plan["slides"]):
        slides.append(content(s, i + 2, total, on_blue=(i % 2 == 1)))
    slides.append(cta(plan, subj, total))
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("slide-*.*"):
        old.unlink()
    paths = []
    for i, im in enumerate(slides, 1):
        p = out_dir / f"slide-{i}.jpg"
        im.save(p, "JPEG", quality=92, optimize=True)
        paths.append(p)
    slides[0].save(out_dir / "carosello.pdf", save_all=True, append_images=slides[1:],
                   resolution=144, quality=90, title=pdf_title(plan), author="Federico Batildi")
    # anteprima: tutte le slide affiancate
    thumb_w = 360
    sheet = Image.new("RGB", (thumb_w * len(slides) + 20 * (len(slides) + 1), int(thumb_w * H / W) + 40), (40, 40, 40))
    for i, im in enumerate(slides):
        sheet.paste(im.resize((thumb_w, int(thumb_w * H / W)), Image.LANCZOS), (20 + i * (thumb_w + 20), 20))
    sheet.save(out_dir / "anteprima.jpg", quality=88)
    return paths


def pdf_title(plan: dict) -> str:
    c = plan["cover"]
    return f"{c['title_big']} — {c['title_rest']}"


def _save_subject(src: Path):
    """Il soggetto si tiene in PNG (serve la trasparenza) ma ridimensionato: repo leggero."""
    im = Image.open(src)
    im.thumbnail((1400, 1800), Image.LANCZOS)
    im.save(src, optimize=True)


def build_carousel(item_id: str) -> Path:
    """Testi nuovi + soggetto nuovo + impaginazione (costa ~3 crediti Higgsfield)."""
    out_dir = CAROUSEL_DIR / item_id
    plan = plan_carousel(item_id)
    subject = out_dir / "soggetto.png"
    plan["subject_job"] = generate_subject(plan["cover"]["subject_en"], subject)
    _save_subject(subject)
    save_plan(item_id, plan)
    render(plan, subject, out_dir)
    return out_dir


def save_plan(item_id: str, plan: dict) -> None:
    out_dir = CAROUSEL_DIR / item_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "carosello.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")


def load_plan(item_id: str) -> dict | None:
    p = CAROUSEL_DIR / item_id / "carosello.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def update_texts(item_id: str, edited: dict) -> Path:
    """Testi modificati a mano → nuova impaginazione, stessa immagine (gratis)."""
    plan = load_plan(item_id)
    if not plan:
        raise FileNotFoundError("carosello non ancora generato")
    for key in ("cover", "cta"):
        plan[key].update({k: v for k, v in (edited.get(key) or {}).items() if isinstance(v, str)})
    if isinstance(edited.get("slides"), list):
        plan["slides"] = [{"title": s.get("title", ""), "lines": [l for l in s.get("lines", []) if l.strip()],
                           "highlight": s.get("highlight", ""), "tags": [t for t in s.get("tags", []) if t.strip()]}
                          for s in edited["slides"]][:3]
    save_plan(item_id, plan)
    out_dir = CAROUSEL_DIR / item_id
    render(plan, out_dir / "soggetto.png", out_dir)
    return out_dir


def _fresh_subject(item_id: str, plan: dict) -> tuple[str, str]:
    """Nuova direzione + nuovo soggetto per lo stesso tema (stessi testi)."""
    previous = previous_subjects()   # include anche questo carosello: niente ripetizioni
    direction = pick_direction(previous)
    avoid = "\n".join(f"- {p['subject']}" for p in previous if p["subject"])
    c = plan["cover"]
    prompt = (f"Tema del carosello LinkedIn: {c['kicker']} — {c['title_big']} {c['title_rest']} "
              f"({c['script_accent']}).\nInventa in INGLESE il soggetto visivo della copertina: una "
              f"metafora visiva forte, stile collage editoriale, collegata al tema. Direzione obbligatoria: "
              f"{direction}. Nessuna persona reale riconoscibile, niente testo o loghi, un solo soggetto ben "
              f"scontornabile con spazio in alto. Deve essere diverso da:\n{avoid}")
    out, _ = run_claude(prompt, {"type": "object", "properties": {"subject_en": {"type": "string"}},
                                 "required": ["subject_en"]},
                        model="sonnet", timeout=300, system="Rispondi solo con dati conformi allo schema JSON.")
    return direction, out["subject_en"]


def new_subject(item_id: str, subject_en: str | None = None) -> Path:
    """Nuova immagine per lo stesso carosello (stessi testi, nuovo soggetto), ~3 crediti."""
    plan = load_plan(item_id)
    if not plan:
        raise FileNotFoundError("carosello non ancora generato")
    if subject_en:
        plan["cover"]["subject_en"] = subject_en
    else:
        plan["direction"], plan["cover"]["subject_en"] = _fresh_subject(item_id, plan)
    out_dir = CAROUSEL_DIR / item_id
    plan["subject_job"] = generate_subject(plan["cover"]["subject_en"], out_dir / "soggetto.png")
    _save_subject(out_dir / "soggetto.png")
    save_plan(item_id, plan)
    render(plan, out_dir / "soggetto.png", out_dir)
    return out_dir


def carousel_files(item_id: str) -> list[str]:
    """Percorsi (relativi al repo) da salvare su GitHub."""
    out_dir = CAROUSEL_DIR / item_id
    return [str(p.relative_to(ROOT)) for p in sorted(out_dir.glob("*")) if p.is_file()]

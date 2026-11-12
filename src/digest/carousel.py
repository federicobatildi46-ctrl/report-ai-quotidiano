"""Caroselli LinkedIn (6 slide, 1080×1350) nello stile dei riferimenti Pinterest di Federico:
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
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

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

def title_font(text: str, max_w: int, sizes, max_lines: int = 2):
    """Primo corpo Anton (tra `sizes`) con cui il titolo sta in `max_lines` righe e nessuna riga
    (nemmeno una parola lunga tipo FREE-CLAUDE-CODE) esce dalla pagina."""
    for s in sizes:
        f = anton(s)
        lines = wrap(f, text, max_w)
        if len(lines) <= max_lines and all(text_w(f, l) <= max_w for l in lines):
            return f, lines
    s = sizes[-1]
    while s > 40:   # ultima risorsa: si rimpicciolisce finché ogni riga entra
        s -= 6
        f = anton(s)
        lines = wrap(f, text, max_w)
        if all(text_w(f, l) <= max_w for l in lines):
            break
    return f, lines


def _mask_of(subj: Image.Image, xy) -> Image.Image:
    m = Image.new("L", (W, H), 0)
    m.paste(subj.getchannel("A"), xy)
    return m


def _accent_layer(text: str, size: int) -> Image.Image:
    acc = script(size)
    layer = Image.new("RGBA", (text_w(acc, text) + 60, int(size * 1.9)), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20, 10), text, font=acc, fill=YELLOW)
    return layer.rotate(7, expand=True, resample=Image.BICUBIC)


def _overlaps(mask: Image.Image, layer: Image.Image, xy, margin: int = 19) -> bool:
    """True se le lettere del corsivo (con un po' di respiro) toccano il soggetto."""
    x, y = xy
    letters = layer.getchannel("A").point(lambda v: 255 if v > 30 else 0).filter(ImageFilter.MaxFilter(margin))
    under = mask.crop((x, y, x + layer.width, y + layer.height)).point(lambda v: 255 if v > 30 else 0)
    return ImageChops.multiply(letters, under).getbbox() is not None


def cover(plan: dict, subj: Image.Image, total: int) -> Image.Image:
    c = plan["cover"]
    img = background(BLUE).convert("RGBA")
    d = ImageDraw.Draw(img)
    header(img, True)
    spaced(d, (M, 150), c["kicker"].upper(), inter(30, 800), WHITE, tracking=4)
    # titolone (dietro al soggetto)
    big_text = c["title_big"].upper()
    big = fit(anton, big_text, W - 2 * M, 380)
    d.text((M - 6, 175), big_text, font=big, fill=WHITE)
    big_bottom = 175 + big.getbbox(big_text)[3]
    # resto del titolo su fascia nera: stesso margine sopra e sotto le lettere
    rest_text = c["title_rest"].upper()
    rest = fit(anton, rest_text, W - 2 * M - 24, 84)
    ry = big_bottom + 14
    rb = d.textbbox((M, ry), rest_text, font=rest)
    pad = 12
    band = (rb[0] - pad, rb[1] - pad, rb[2] + pad, rb[3] + pad)
    acc_y = band[3] + 20

    # soggetto grande in primo piano, ancorato in basso a destra: il corsivo NON deve mai
    # coprirlo → si prova prima a rimpicciolire il corsivo, poi il soggetto.
    top = big_bottom - 150
    base = subj.copy()
    base.thumbnail((int(W * 0.92), H + 60 - top), Image.LANCZOS)
    choice = None
    for scale in (1.0, 0.92, 0.85, 0.78, 0.7, 0.62):
        s = base.resize((int(base.width * scale), int(base.height * scale)), Image.LANCZOS) if scale < 1 else base
        xy = (W - s.width + 40, H + 60 - s.height)
        mask = _mask_of(s, xy)
        for size in (118, 104, 92):
            layer = _accent_layer(c["script_accent"], size)
            if not _overlaps(mask, layer, (M - 10, acc_y)):
                choice = (s, xy, layer)
                break
        if choice:
            break
    if not choice:   # caso estremo: soggetto piccolo e corsivo minimo
        s = base.resize((int(base.width * 0.55), int(base.height * 0.55)), Image.LANCZOS)
        choice = (s, (W - s.width + 40, H + 60 - s.height), _accent_layer(c["script_accent"], 80))
    s, xy, layer = choice
    paste_with_shadow(img, s, xy)
    d = ImageDraw.Draw(img)
    d.rectangle(band, fill=INK)
    d.text((M, ry), rest_text, font=rest, fill=WHITE)
    img.paste(layer, (M - 10, acc_y), layer)
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
PILL_H, PILL_GAP = 58, 72


def _pill_rows(tags) -> int:
    f = inter(30, 700)
    x, rows = M, 1
    for t in tags[:3]:
        w = text_w(f, t) + 48
        if x + w > W - M:
            x, rows = M, rows + 1
        x += w + 16
    return rows


def pills(d, tags, y, on_blue) -> int:
    """Etichette colorate a pillola (stile secondo riferimento). Ritorna la y sotto le pillole."""
    f = inter(30, 700)
    x = M
    for i, t in enumerate(tags[:3]):
        w = text_w(f, t) + 48
        if x + w > W - M:
            x, y = M, y + PILL_GAP
        color = PILL_COLORS[i % len(PILL_COLORS)]
        if not on_blue and color == WHITE:
            color = INK
        d.rounded_rectangle((x, y, x + w, y + PILL_H), radius=29, fill=color,
                            outline=INK if not on_blue else None, width=2)
        d.text((x + 24, y + 12), t, font=f, fill=WHITE if color == INK else INK)
        x += w + 16
    return y + PILL_H


# Spazio utile delle slide di contenuto: sotto l'intestazione e sopra la barra in basso.
CONTENT_TOP, CONTENT_BOTTOM = 115, H - 140
# Dal più grande al più piccolo: si usa il primo con cui tutto entra nello spazio utile.
CONTENT_PRESETS = [
    # titoli, corpo, interlinea, spazio tra punti, evidenziatore
    {"title": (150, 130, 120), "body": 46, "lh": 62, "gap": 26, "hl": 42},
    {"title": (124, 112, 104), "body": 42, "lh": 56, "gap": 20, "hl": 38},
    {"title": (104, 96, 88), "body": 38, "lh": 50, "gap": 16, "hl": 34},
    {"title": (88, 80, 72), "body": 34, "lh": 45, "gap": 12, "hl": 31},
]


def _content_layout(slide: dict, p: dict) -> dict:
    title = slide["title"].upper()
    tf, tlines = title_font(title, W - 2 * M, p["title"], max_lines=2)
    body = inter(p["body"], 500)
    blines = [wrap(body, line, W - 2 * M - 64) for line in slide["lines"]]
    hf_ = inter(p["hl"], 800)
    hl = wrap(hf_, slide["highlight"], W - 2 * M - 60) if slide.get("highlight") else []
    hl_lh = p["hl"] + 14
    tags = slide.get("tags") or []
    pill_h = (_pill_rows(tags) - 1) * PILL_GAP + PILL_H if tags else 0
    block = (50 + len(tlines) * (tf.size + 14) + 30
             + sum(len(b) * p["lh"] + p["gap"] for b in blines)
             + (4 + pill_h + 36 if tags else 0)
             + (len(hl) * hl_lh + 36 if hl else 0))
    return {"p": p, "tf": tf, "tlines": tlines, "body": body, "blines": blines, "hf": hf_,
            "hl": hl, "hl_lh": hl_lh, "tags": tags, "block": block}


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

    # il preset più grande con cui tutto entra tra intestazione e barra, poi centrato
    space = CONTENT_BOTTOM - CONTENT_TOP
    for p in CONTENT_PRESETS:
        L = _content_layout(slide, p)
        if L["block"] <= space:
            break
    p = L["p"]
    y = CONTENT_TOP + max(0, (space - L["block"]) // 2)

    spaced(d, (M, y), num, inter(30, 800), accent, tracking=4)
    y += 50
    for line in L["tlines"]:
        d.text((M - 4, y), line, font=L["tf"], fill=accent)
        y += L["tf"].size + 14
    y += 30
    arrow = inter(p["body"], 700)
    for parts in L["blines"]:
        for i, part in enumerate(parts):
            if i == 0:
                d.text((M, y), "→", font=arrow, fill=YELLOW if on_blue else BLUE)
            d.text((M + 64, y), part, font=L["body"], fill=fg)
            y += p["lh"]
        y += p["gap"]
    if L["tags"]:
        y = pills(d, L["tags"], y + 4, on_blue) + 36
    if L["hl"]:
        box_h = len(L["hl"]) * L["hl_lh"] + 36
        d.rectangle((M, y, W - M, y + box_h), fill=YELLOW)
        for i, part in enumerate(L["hl"]):
            d.text((M + 30, y + 18 + i * L["hl_lh"]), part, font=L["hf"], fill=INK)
    footer(img, n, total, on_blue)
    return img


def pain(p: dict, n: int, total: int) -> Image.Image:
    """Slide "quanto ti costa non farlo": pain point con le stime, soluzione e guadagno stimato."""
    img = background(PAPER)
    d = ImageDraw.Draw(img)
    wf = anton(760)   # "€" in filigrana in alto a destra, tagliato dal bordo, dietro al titolo
    d.text((W - int(text_w(wf, "€") * 0.72), -40), "€", font=wf, fill=PAPER_DARK)
    header(img, False)
    d = ImageDraw.Draw(img)

    points = [x for x in (p.get("points") or []) if (x.get("figure") or x.get("text"))][:3]
    title = (p.get("title") or "").upper()
    tf, tlines = title_font(title, W - 2 * M, (108, 96, 90), max_lines=2)
    fig_w = 330
    txt = inter(34, 600)
    rows = []
    for x in points:
        ff = fit(anton, (x.get("figure") or "").upper(), fig_w, 76, 40)
        tl = wrap(txt, x.get("text") or "", W - 2 * M - fig_w - 30)
        rows.append((ff, tl, max(ff.size + 10, len(tl) * 44 + 6)))
    sol = inter(34, 700)
    sol_lines = wrap(sol, p.get("solution") or "", W - 2 * M - 70)
    gain_f = fit(anton, (p.get("gain") or "").upper(), W - 2 * M - 70, 110, 60)
    gt = inter(32, 500)
    gt_lines = wrap(gt, p.get("gain_text") or "", W - 2 * M - 70)
    box_h = 36 + len(sol_lines) * 44 + 8 + gain_f.size + 22 + len(gt_lines) * 42 + 30
    note_f = inter(24, 500)
    note_lines = wrap(note_f, p.get("note") or "", W - 2 * M)
    block = (50 + len(tlines) * (tf.size + 10) + 30 + sum(r[2] + 26 for r in rows) + 30
             + box_h + 22 + len(note_lines) * 32)
    y = max(130, 110 + (H - 270 - block) // 2)

    spaced(d, (M, y), (p.get("kicker") or "").upper(), inter(28, 800), BLUE, tracking=4)
    y += 50
    for line in tlines:
        d.text((M - 4, y), line, font=tf, fill=INK)
        y += tf.size + 10
    y += 30
    for x, (ff, tl, rh) in zip(points, rows):
        d.line((M, y, W - M, y), fill=INK, width=2)
        y += 18
        d.text((M, y - 6), (x.get("figure") or "").upper(), font=ff, fill=BLUE)
        ty = y + max(0, (ff.size - len(tl) * 44) // 2)
        for i, part in enumerate(tl):
            d.text((M + fig_w + 30, ty + i * 44), part, font=txt, fill=INK)
        y += rh + 8
    d.line((M, y, W - M, y), fill=INK, width=2)
    y += 30
    # soluzione: riquadro blu con il guadagno stimato in giallo
    d.rectangle((M, y, W - M, y + box_h), fill=BLUE)
    by = y + 36
    for part in sol_lines:
        d.text((M + 35, by), part, font=sol, fill=WHITE)
        by += 44
    by += 8
    d.text((M + 32, by - 10), (p.get("gain") or "").upper(), font=gain_f, fill=YELLOW)
    by += gain_f.size + 22
    for part in gt_lines:
        d.text((M + 35, by), part, font=gt, fill=WHITE)
        by += 42
    y += box_h + 22
    for part in note_lines:
        d.text((M, y), part, font=note_f, fill=(95, 95, 95))
        y += 32
    footer(img, n, total, False)
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
    tf, tlines = title_font(c["title"].upper(), W - 2 * M, (130, 116, 104, 92), max_lines=3)
    y = 200
    for line in tlines:
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
        "pain": {"type": "object", "properties": {
            "kicker": {"type": "string"}, "title": {"type": "string"},
            "points": {"type": "array", "items": {"type": "object", "properties": {
                "figure": {"type": "string"}, "text": {"type": "string"}}, "required": ["figure", "text"]}},
            "solution": {"type": "string"}, "gain": {"type": "string"}, "gain_text": {"type": "string"},
            "note": {"type": "string"}},
            "required": ["kicker", "title", "points", "solution", "gain", "gain_text", "note"]},
        "cta": {"type": "object", "properties": {
            "title": {"type": "string"}, "text": {"type": "string"}, "keyword": {"type": "string"}},
            "required": ["title", "text", "keyword"]},
    },
    "required": ["cover", "slides", "pain", "cta"],
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
    has_pain = bool(plan.get("pain"))   # i caroselli fatti prima di novembre 2026 non l'hanno
    total = 2 + len(plan["slides"]) + has_pain
    slides = [cover(plan, subj, total)]
    for i, s in enumerate(plan["slides"]):
        slides.append(content(s, i + 2, total, on_blue=(i % 2 == 1)))
    if has_pain:
        slides.append(pain(plan["pain"], len(slides) + 1, total))
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
    if isinstance(edited.get("pain"), dict):
        e = edited["pain"]
        plan["pain"] = {**(plan.get("pain") or {}),
                        **{k: v for k, v in e.items() if isinstance(v, str)},
                        "points": [{"figure": str(x.get("figure", "")).strip(), "text": str(x.get("text", "")).strip()}
                                   for x in e.get("points") or [] if x.get("figure") or x.get("text")][:3]}
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

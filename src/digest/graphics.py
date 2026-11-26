"""Elementi grafici del report in stile editoriale (nero, carta, arancione, retino a puntini).

- `halftone_band` / `halftone_corner`: il retino arancione (puntini che si rimpiccioliscono),
  usato nell'app (web/img/) e nell'email.
- `masthead`: la testata dell'email (giorno in titolo condensato + retino), come immagine:
  Gmail non carica font personalizzati, così il titolo è identico ovunque.
"""

import io
import math
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from digest import ROOT

ORANGE = (255, 84, 22)
INK = (14, 14, 14)
PAPER = (244, 243, 239)
WHITE = (255, 255, 255)
FONTS = ROOT / "assets" / "fonts"
WEB_IMG = ROOT / "web" / "img"

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]


def bebas(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "BebasNeue-Regular.ttf"), size)


def inter(size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / "Inter[opsz,wght].ttf"), size)
    f.set_variation_by_axes([min(max(size, 14), 32), weight])
    return f


def _dots(w: int, h: int, step: int, strength, color=ORANGE, scale: int = 3) -> Image.Image:
    """Retino: per ogni cella un puntino di raggio proporzionale a strength(x, y) in [0, 1].
    Disegnato più grande e poi ridotto, per bordi morbidi."""
    img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = step * scale
    for row, y in enumerate(range(0, h * scale + s, s)):
        off = s / 2 if row % 2 else 0          # griglia sfalsata, come la stampa
        for x in range(0, w * scale + s, s):
            cx, cy = x + off, y
            fx, fy = min(1.0, cx / (w * scale)), min(1.0, cy / (h * scale))   # le celle oltre il bordo restano a 1
            k = max(0.0, min(1.0, strength(fx, fy)))
            r = k * s * 0.62
            if r > 0.6 * scale:
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (255,))
    return img.resize((w, h), Image.LANCZOS)


def halftone_band(w: int = 1600, h: int = 120, step: int = 12) -> Image.Image:
    """Fascia orizzontale: a gradini, come le barre del riferimento (piena a destra, svanisce a sinistra)."""
    def strength(x, y):
        bars = 7
        level = (math.floor(x * bars) + 1) / bars            # gradini crescenti verso destra
        top = 1 - level                                        # ogni gradino sale un po' di più
        return 0 if y < top * 0.9 else (x ** 1.4) * (0.35 + 0.65 * (y - top * 0.9) / max(0.1, 1 - top * 0.9))
    return _dots(w, h, step, strength)


def halftone_corner(w: int = 900, h: int = 700, step: int = 16) -> Image.Image:
    """Macchia di retino che parte dall'angolo in alto a destra e sfuma."""
    def strength(x, y):
        dist = math.hypot((1 - x) * 1.0, y * 1.25)
        return max(0.0, 1.05 - dist * 1.15)
    return _dots(w, h, step, strength)


def halftone_top(w: int = 1600, h: int = 420, step: int = 16) -> Image.Image:
    """Retino dall'alto verso il basso, più denso a destra (testata scura, come la copertina)."""
    def strength(x, y):
        return max(0.0, (1 - y) ** 1.6 * (0.25 + 0.95 * x ** 1.3))
    return _dots(w, h, step, strength)


def write_web_assets() -> list[Path]:
    """Immagini statiche dell'app (web/img/). Rigenerabili: `uv run python -m digest.graphics`."""
    WEB_IMG.mkdir(parents=True, exist_ok=True)
    out = []
    for name, im in (("retino-fascia.png", halftone_band()), ("retino-angolo.png", halftone_corner()),
                     ("retino-testata.png", halftone_top())):
        p = WEB_IMG / name
        im.save(p, optimize=True)
        out.append(p)
    return out


def masthead(report: dict, width: int = 1280) -> bytes:
    """Testata dell'email: blocco nero, retino arancione in alto, giorno enorme in Bebas Neue."""
    d = date.fromisoformat(report["date"])
    s = report["stats"]
    h = int(width * 0.5)
    img = Image.new("RGB", (width, h), INK).convert("RGBA")
    dots = halftone_top(width, int(h * 0.72), step=18)
    img.alpha_composite(dots, (0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(width * 0.055)
    draw.text((pad, pad - 6), f"REPORT AI  ·  {d.year}", font=inter(26, 800), fill=WHITE)
    title = f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}".upper()
    size = 240
    while size > 80 and bebas(size).getlength(title) > width - 2 * pad:
        size -= 6
    f = bebas(size)
    bottom = h - pad - 46
    draw.text((pad - 4, bottom - f.getbbox(title)[3]), title, font=f, fill=WHITE)
    line = f"{s['stories']} NOTIZIE   ·   CIRCA {report['reading_minutes']} MINUTI   ·   {s['collected']} ELEMENTI LETTI"
    draw.text((pad, h - pad - 22), line, font=inter(24, 700), fill=ORANGE)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def band_png(width: int = 1280, height: int = 64) -> bytes:
    buf = io.BytesIO()
    halftone_band(width, height, step=10).save(buf, "PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    for p in write_web_assets():
        print(p)

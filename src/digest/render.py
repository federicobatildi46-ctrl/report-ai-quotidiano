"""Fase 3 — il report in HTML, pensato per Gmail (desktop e telefono).

Stile editoriale "brochure" (come l'app): nero, carta, un solo accento arancione, retino a
puntini, numeri grandi 01/02/03, angoli vivi. Gmail non carica font personalizzati, quindi la
testata con il titolo condensato è un'immagine (src/digest/graphics.py) e i titoli di sezione
usano font condensati di sistema.

Immagini: nell'email sono allegate "in linea" (cid:...), nel file reports/AAAA-MM-GG.html sono
incorporate (data:), così il file si apre da solo con doppio click.

Regole per le email: stili inline (Gmail ignora molto del CSS in <head>), niente JavaScript,
larghezza massima 680px, HTML compatto (Gmail taglia i messaggi oltre ~102 KB).
"""

import base64
import re
from datetime import date
from html import escape

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]

APP_URL = "http://localhost:8787"

INK, MUTED, LINE, BG, CARD = "#0e0e0e", "#6b6a66", "#dddbd4", "#efeeea", "#fbfaf8"
ORANGE, ORANGE_SOFT, DARK_MUTED, DARK_LINE = "#ff5416", "#ffe9df", "#9d9b95", "#2a2a28"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
CONDENSED = "'Bebas Neue','Oswald','Arial Narrow','Helvetica Neue Condensed',Arial,sans-serif"
EYEBROW = "font-size:10.5px;font-weight:800;letter-spacing:.14em;text-transform:uppercase"

BADGES = {  # etichetta, colore
    "ufficiale": ("Ufficiale", "#17703f"),
    "confermata": ("Confermata", "#1c4f8f"),
    "da_verificare": ("Da verificare", "#b2520a"),
    "smentita": ("Smentita", "#b3261e"),
    "dal_repo": ("Dal progetto", "#55534e"),
}
BADGE_PLURAL = {"ufficiale": "ufficiali", "confermata": "confermate", "da_verificare": "da verificare",
                "smentita": "smentite", "dal_repo": "dal progetto"}


def data_italiana(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]} {d.year}"


def app_link(day: str, item_id: str = "") -> str:
    return f"{APP_URL}/#{day}" + (f"/{item_id}" if item_id else "")


def email_images(r: dict) -> dict[str, bytes]:
    """Immagini dell'email: testata del giorno + fascia di retino (identificativo → PNG)."""
    from digest.graphics import band_png, masthead
    return {"testata": masthead(r), "retino": band_png()}


def _src(images: dict | None, key: str) -> str:
    """cid:… nell'email (images=None), data:… nel file html (images = i byte)."""
    if images is None:
        return f"cid:{key}"
    return "data:image/png;base64," + base64.b64encode(images[key]).decode()


def _badge(key: str, dark: bool = False) -> str:
    label, color = BADGES.get(key, BADGES["da_verificare"])
    if dark:
        color = "#ffffff"
    return (f'<span style="display:inline-block;padding:2px 7px;border:1px solid {color};color:{color};'
            f'font-size:10px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap">'
            f'<span style="display:inline-block;width:6px;height:6px;background:{color};margin:0 6px 1px 0"></span>{label}</span>')


def _stars(n) -> str:
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n)


def _source(s: dict) -> str:
    meta = s.get("meta") or {}
    extra = f" ★ {_stars(meta['stars'])}" if meta.get("stars_verified") else ""
    return f'<a href="{escape(s["url"], quote=True)}" style="color:{MUTED}">{escape(s["name"])}</a>{extra}'


def _item(it: dict, day: str, pick_labels: dict) -> str:
    sources = " · ".join(_source(s) for s in it["sources"])
    ribbon = "".join(
        f'<div style="margin:0 0 10px"><span style="{EYEBROW};color:#ffffff;background:{ORANGE};padding:3px 8px">'
        f'{escape(label)}</span></div>' for label in pick_labels.get(it["id"], []))
    points = ""
    if it.get("key_points"):
        points = ('<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 12px">'
                  + "".join(f'<tr><td style="vertical-align:top;padding:9px 10px 0 0"><div style="width:8px;height:2px;'
                            f'background:{ORANGE}"></div></td><td style="font-size:14.5px;line-height:1.55;color:{INK};'
                            f'padding:0 0 4px">{escape(p)}</td></tr>' for p in it["key_points"])
                  + "</table>")
    return (
        f'<div style="padding:22px 0;border-top:1px solid {LINE}">{ribbon}'
        f'<div style="font-size:19px;line-height:1.28;font-weight:800;letter-spacing:-.01em;margin:0 0 10px">'
        f'<a href="{escape(it["primary_url"], quote=True)}" style="color:{INK};text-decoration:none">{escape(it["title"])}</a></div>'
        f'<div style="margin:0 0 12px;line-height:1.8">{_badge(it["badge"])}'
        f'<span style="color:{MUTED};font-size:12.5px"> &nbsp;{escape(it["badge_note"])}</span></div>'
        f'<div style="font-size:15.5px;line-height:1.6;color:{INK};margin:0 0 12px">{escape(it["summary"])}</div>'
        f'{points}'
        f'<div style="font-size:14.5px;line-height:1.55;color:{INK};border-left:3px solid {ORANGE};padding:1px 0 1px 13px;margin:0 0 8px">'
        f'<span style="{EYEBROW};color:{ORANGE}">Perché ti serve</span> &nbsp;{escape(it["why"])}</div>'
        + (f'<div style="font-size:14.5px;line-height:1.55;color:{INK};background:{ORANGE_SOFT};border-left:3px solid {INK};'
           f'padding:9px 13px;margin:10px 0 8px"><span style="{EYEBROW};color:{INK}">Idea Short</span> &nbsp;«{escape(it["short_hook"])}»</div>'
           if it.get("short_hook") else "") +
        f'<div style="font-size:12.5px;line-height:1.6;color:{MUTED};margin:12px 0 0">Fonti: {sources}'
        f' &nbsp;·&nbsp; <a href="{app_link(day, it["id"])}" style="color:{ORANGE};font-weight:800;'
        f'text-decoration:none">Apri nell\'app&nbsp;→</a></div>'
        f'</div>')


def _section(sec: dict, n: int, day: str, pick_labels: dict, band: str) -> str:
    main, _, rest = sec["title"].partition(":")
    head = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>'
        f'<td style="vertical-align:bottom;width:1%;white-space:nowrap;padding:0 14px 0 0;font-family:{CONDENSED};'
        f'font-size:54px;line-height:.85;font-weight:700;color:{ORANGE}">{n:02d}</td>'
        f'<td style="vertical-align:bottom">'
        + (f'<div style="{EYEBROW};color:{MUTED};margin:0 0 4px">{escape(rest.strip())}</div>' if rest.strip() else "")
        + f'<div style="font-family:{CONDENSED};font-size:32px;line-height:.92;font-weight:700;text-transform:uppercase;'
          f'letter-spacing:-.01em;color:{INK}">{escape(main.strip())}</div></td>'
        f'<td style="vertical-align:bottom;text-align:right;font-family:{CONDENSED};font-size:30px;line-height:.85;'
        f'font-weight:700;color:{MUTED}">{len(sec["items"]):02d}</td></tr></table>'
        f'<img src="{band}" width="616" alt="" style="display:block;width:100%;max-width:616px;height:auto;margin:12px 0 0;border:0">')
    groups: dict[str, list[dict]] = {}
    for it in sec["items"]:
        groups.setdefault(it.get("subsection") or "", []).append(it)
    pos = {id(it): i for i, it in enumerate(sec["items"])}
    keys = sorted(groups, key=lambda k: min(pos[id(i)] for i in groups[k]))
    body = ""
    for k in keys:
        label = groups[k][0].get("subsection_label") or ""
        items = "".join(_item(it, day, pick_labels) for it in groups[k])
        if label and len(keys) > 1:
            body += (f'<div style="{EYEBROW};color:{ORANGE};padding:16px 0 0;border-top:1px solid {INK}">{escape(label)}</div>'
                     + items.replace(f"border-top:1px solid {LINE}", "border-top:0", 1))
        else:
            body += items
    return (f'<div style="background:{CARD};border-top:3px solid {INK};padding:20px 24px 4px;margin:0 0 22px">'
            f'{head}{body}</div>')


def _pick_block(kind: str, pk: dict, day: str) -> str:
    is_post = kind == "linkedin"
    label = "Post LinkedIn del giorno" if is_post else "Short del giorno"
    cta = "Apri nell'app e genera il post" if is_post else "Apri nell'app e genera lo script"
    rows = ""
    for key, title in (("target", "A chi parla"), ("pain", "Il problema"), ("angle", "L'angolo")):
        if is_post and pk.get(key):
            rows += (f'<div style="margin:0 0 7px"><span style="{EYEBROW};color:#ffffff">{title}</span>'
                     f' &nbsp;{escape(pk[key])}</div>')
    rows += f'<div style="margin:0 0 7px"><span style="{EYEBROW};color:#ffffff">Perché oggi</span> &nbsp;{escape(pk["why"])}</div>'
    if pk.get("caveat"):
        rows += (f'<div style="margin:10px 0 0;padding:9px 11px;border-left:3px solid {ORANGE};background:#2a160d;'
                 f'color:#ffd6c4"><span style="{EYEBROW};color:{ORANGE}">Prima di pubblicare</span> &nbsp;{escape(pk["caveat"])}</div>')
    alts = ""
    if pk.get("alternatives"):
        alts = (f'<div style="font-size:12.5px;color:{DARK_MUTED};margin:12px 0 0">In alternativa: '
                + " · ".join(f'<a href="{app_link(day, a["item_id"])}" style="color:#d8d6d0">{escape(a["title"])}</a>'
                             for a in pk["alternatives"]) + '</div>')
    return (
        f'<div style="padding:20px 24px;border-top:1px solid {DARK_LINE}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse"><tr>'
        f'<td style="vertical-align:top"><div style="{EYEBROW};color:#ffffff;margin:0 0 8px">{label}</div>{_badge(pk["badge"], dark=True)}</td>'
        f'<td style="vertical-align:top;text-align:right;font-family:{CONDENSED};font-size:52px;line-height:.85;font-weight:700;'
        f'color:{ORANGE};white-space:nowrap">{pk["score"]}<span style="font-size:22px;color:{DARK_MUTED}">/10</span></td></tr></table>'
        f'<div style="font-size:19px;line-height:1.28;font-weight:800;margin:14px 0 12px">'
        f'<a href="{app_link(day, pk["item_id"])}" style="color:#ffffff;text-decoration:none">{escape(pk["title"])}</a></div>'
        f'<div style="font-size:16.5px;line-height:1.45;font-weight:600;color:#ffffff;border-left:3px solid {ORANGE};'
        f'padding:0 0 0 13px;margin:0 0 14px">«{escape(pk["hook"])}»</div>'
        f'<div style="font-size:14px;line-height:1.55;color:#d8d6d0">{rows}</div>'
        f'<div style="margin:16px 0 0"><a href="{app_link(day, pk["item_id"])}" style="display:inline-block;'
        f'background:{ORANGE};color:#ffffff;font-size:13.5px;font-weight:800;text-decoration:none;padding:10px 16px">'
        f'{cta}&nbsp;→</a></div>{alts}</div>')


def _picks(r: dict) -> str:
    if "picks" not in r:   # report fatti prima che esistessero le scelte del giorno
        return ""
    picks, day = r.get("picks") or {}, r["date"]
    body = "".join(_pick_block(k, picks[k], day) for k in ("linkedin", "short") if picks.get(k))
    if not picks.get("linkedin") and r["stats"]["stories"]:
        body = (f'<div style="padding:14px 24px;border-top:1px solid {DARK_LINE};font-size:14.5px;line-height:1.55;'
                f'color:{DARK_MUTED}"><b style="color:#ffffff">Oggi nessun post LinkedIn.</b> Nessuna notizia è '
                f'abbastanza forte per la tua nicchia: meglio saltare un giorno che forzare.</div>') + body
    if not body:
        return ""
    return (f'<div style="background:{INK};color:#ffffff;margin:0 0 22px">'
            f'<div style="padding:22px 24px 16px;font-family:{CONDENSED};font-size:34px;line-height:.9;font-weight:700;'
            f'text-transform:uppercase;color:#ffffff">Da pubblicare oggi</div>{body}</div>')


def _checks(s: dict) -> str:
    c = s.get("checks")
    if not c:
        return ""
    bits = [f"{c['links_tested']} link testati ({c['links_ok']} funzionanti"
            + (f", {c['links_unverifiable']} su siti che non si fanno controllare dai robot" if c["links_unverifiable"] else "")
            + ")"]
    if c.get("repos_verified"):
        bits.append(f"{c['repos_verified']} repo verificate ora su GitHub (stelle ★, date, licenza)")
    badges = ", ".join(f"{n} {BADGE_PLURAL.get(b, b)}" for b, n in c.get("badges", {}).items())
    if badges:
        bits.append(f"fact check: {badges}")
    return f'<div><span style="{EYEBROW};color:{INK}">Controlli</span> &nbsp;{escape(" · ".join(bits))}.</div>'


def to_html(r: dict, images: dict | None = None) -> str:
    """`images=None` → email (immagini cid:), altrimenti i byte delle immagini da incorporare."""
    s, day = r["stats"], r["date"]
    picks = r.get("picks") or {}
    pick_labels: dict[str, list[str]] = {}
    for key, label in (("linkedin", "Post LinkedIn del giorno"), ("short", "Short del giorno")):
        if picks.get(key):
            pick_labels.setdefault(picks[key]["item_id"], []).append(label)
    d = date.fromisoformat(day)
    title = f"{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]}"

    breve = "".join(
        f'<tr><td style="vertical-align:top;padding:4px 16px 14px 0;font-family:{CONDENSED};font-size:40px;line-height:.85;'
        f'font-weight:700;color:{ORANGE};white-space:nowrap">0{n}</td>'
        f'<td style="vertical-align:top;padding:0 0 14px;font-size:15.5px;line-height:1.5;color:{INK};'
        f'border-bottom:{"1px solid " + LINE if n < len(r["in_breve"]) else "0"}">{escape(x)}</td></tr>'
        for n, x in enumerate(r["in_breve"], 1))
    full = [sec for sec in r["sections"] if sec["items"]]
    empty = [sec["title"].split(":")[0] for sec in r["sections"] if not sec["items"]]
    notes = []
    if empty:
        notes.append("Nessuna novità rilevante oggi in: " + ", ".join(empty) + ".")
    if s.get("source_errors"):
        notes.append("Fonti non raggiungibili oggi: " + ", ".join(e["source"] for e in s["source_errors"]) + ".")
    if s.get("dropped_broken_links"):
        notes.append(f"Notizie scartate per link non funzionante: {len(s['dropped_broken_links'])}.")
    footer_notes = "".join(f"<div>{escape(n)}</div>" for n in notes)
    band = _src(images, "retino")

    html = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(r['title'])} — {day}</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:{FONT};color:{INK}">
<div style="max-width:680px;margin:0 auto;padding:18px 10px 10px">
<a href="{app_link(day)}" style="display:block;text-decoration:none"><img src="{_src(images, 'testata')}" width="680"
 alt="Report AI — {title}: {s['stories']} notizie, circa {r['reading_minutes']} minuti"
 style="display:block;width:100%;max-width:680px;height:auto;border:0;background:{INK};color:#ffffff;font-size:22px"></a>
<div style="background:{INK};padding:0 24px 16px;font-size:12.5px;color:{DARK_MUTED};margin:0 0 22px">
{s['discarded']} scartati come rumore &nbsp;·&nbsp; <a href="{app_link(day)}" style="color:{ORANGE};font-weight:800;text-decoration:none">Apri nell'app&nbsp;→</a></div>
{f'''<div style="background:{CARD};border-top:3px solid {INK};padding:18px 24px 6px;margin:0 0 22px">
<div style="{EYEBROW};color:{INK};margin:0 0 14px">In breve</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{breve}</table>
</div>''' if r["in_breve"] else ""}
{_picks(r)}
{''.join(_section(sec, n, day, pick_labels, band) for n, sec in enumerate(full, 1))}
<div style="font-size:12.5px;color:{MUTED};line-height:1.75;padding:14px 4px 26px;border-top:3px solid {INK}">
{_checks(s)}
{footer_notes}
<div><span style="{EYEBROW};color:{INK}">Badge</span> &nbsp;Ufficiale = fonte dell'azienda · Confermata = più fonti indipendenti ·
Da verificare = una sola fonte non ufficiale · Dal progetto = descrizione del progetto, non ancora provato ·
Smentita = smentita da una fonte ufficiale.</div>
<div>Generato con Claude ({escape(s.get('model') or '')}) alle {r['generated_at'][11:16]} UTC.</div>
</div>
</div></body></html>"""
    return re.sub(r">\s+<", "><", html)

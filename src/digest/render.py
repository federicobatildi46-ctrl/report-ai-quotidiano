"""Fase 3 — il report in HTML, pensato per Gmail (desktop e telefono).

Regole per le email: stili inline (Gmail ignora molto del CSS in <head>), niente JavaScript,
larghezza massima 680px, e HTML compatto: Gmail taglia i messaggi oltre ~102 KB.

Design: lo stesso linguaggio dei caroselli (blu elettrico, carta, giallo evidenziatore), gerarchia
netta e una sola cosa da fare per blocco. Ogni notizia ha il link "Apri nell'app", che porta
alla stessa notizia su http://localhost:8787 dove ci sono i pulsanti (lezione, post, Short).
"""

import re
from datetime import date
from html import escape

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]

APP_URL = "http://localhost:8787"

BADGES = {  # etichetta, testo, sfondo
    "ufficiale": ("✅ Ufficiale", "#17603a", "#e2f3e8"),
    "confermata": ("🔁 Confermata", "#1a4f8b", "#e3eefb"),
    "da_verificare": ("⚠️ Da verificare", "#855000", "#fcefd6"),
    "smentita": ("❌ Smentita", "#a12020", "#fbe4e4"),
    "dal_repo": ("📦 Dal progetto", "#454a53", "#ebebe7"),
}
BADGE_PLURAL = {"ufficiale": "ufficiali", "confermata": "confermate", "da_verificare": "da verificare",
                "smentita": "smentite", "dal_repo": "dal progetto"}
ACCENT = {"claude": "#c96442", "higgsfield": "#6d4aff", "elevenlabs": "#14161a",
          "creators": "#d0344e", "github": "#2b3137", "virali": "#c98a00"}

INK, MUTED, LINE, BG, CARD, SOFT = "#14161a", "#646b75", "#e3e1da", "#f3f2ee", "#ffffff", "#f3f2ee"
BLUE, YELLOW, YELLOW_SOFT = "#1e5af0", "#f4e242", "#fdf6c8"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
EYEBROW = "font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase"


def data_italiana(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]} {d.year}"


def app_link(day: str, item_id: str = "") -> str:
    return f"{APP_URL}/#{day}" + (f"/{item_id}" if item_id else "")


def _a(url: str, text: str, style: str = "") -> str:
    return f'<a href="{escape(url, quote=True)}" style="color:{INK};{style}">{escape(text)}</a>'


def _badge(key: str) -> str:
    label, fg, bg = BADGES.get(key, BADGES["da_verificare"])
    return (f'<span style="display:inline-block;padding:2px 9px;border-radius:11px;'
            f'background:{bg};color:{fg};font-size:12px;font-weight:700;white-space:nowrap;'
            f'text-transform:none;letter-spacing:0">{label}</span>')


def _stars(n) -> str:
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n)


def _source(s: dict) -> str:
    meta = s.get("meta") or {}
    extra = f" ★ {_stars(meta['stars'])}" if meta.get("stars_verified") else ""
    return (f'<a href="{escape(s["url"], quote=True)}" style="color:{MUTED}">{escape(s["name"])}</a>'
            f'{extra}')


def _item(it: dict, day: str, pick_labels: dict) -> str:
    sources = " · ".join(_source(s) for s in it["sources"])
    ribbon = "".join(
        f'<div style="{EYEBROW};color:{BLUE};margin:0 0 6px">★ {escape(label)}</div>'
        for label in pick_labels.get(it["id"], []))
    return (
        f'<div style="padding:18px 0;border-top:1px solid {LINE}">{ribbon}'
        f'<div style="font-size:18px;line-height:1.3;font-weight:800;letter-spacing:-.01em;margin:0 0 8px">'
        f'{_a(it["primary_url"], it["title"], "text-decoration:none")}</div>'
        f'<div style="margin:0 0 10px;line-height:1.7">{_badge(it["badge"])}'
        f'<span style="color:{MUTED};font-size:12.5px"> {escape(it["badge_note"])}</span></div>'
        f'<div style="font-size:15.5px;line-height:1.6;color:{INK};margin:0 0 10px">{escape(it["summary"])}</div>'
        + (f'<ul style="margin:0 0 12px;padding:0 0 0 20px;font-size:14.5px;line-height:1.55;color:{INK}">'
           + "".join(f'<li style="margin:0 0 4px">{escape(p)}</li>' for p in it.get("key_points", []))
           + '</ul>' if it.get("key_points") else "") +
        f'<div style="font-size:14.5px;line-height:1.55;color:{INK};background:{SOFT};'
        f'border-left:3px solid {BLUE};border-radius:0 8px 8px 0;padding:9px 12px;margin:0 0 8px">'
        f'<b>Perché ti serve.</b> {escape(it["why"])}</div>'
        + (f'<div style="font-size:14.5px;line-height:1.55;color:{INK};background:{YELLOW_SOFT};'
           f'border-left:3px solid {YELLOW};border-radius:0 8px 8px 0;padding:9px 12px;margin:0 0 8px">'
           f'<b>🎬 Idea Short.</b> «{escape(it["short_hook"])}»</div>'
           if it.get("short_hook") else "") +
        f'<div style="font-size:12.5px;line-height:1.6;color:{MUTED};margin:10px 0 0">Fonti: {sources}'
        f' &nbsp;·&nbsp; <a href="{app_link(day, it["id"])}" style="color:{BLUE};font-weight:700;'
        f'text-decoration:none">Apri nell\'app&nbsp;→</a></div>'
        f'</div>')


def _section(sec: dict, day: str, pick_labels: dict) -> str:
    accent = ACCENT.get(sec["id"], INK)
    head = (f'<div style="padding:0 0 12px"><span style="display:inline-block;width:10px;height:10px;'
            f'border-radius:3px;background:{accent};margin:0 8px 0 0"></span>'
            f'<span style="font-size:13px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;'
            f'color:{INK}">{escape(sec["title"])}</span>'
            f'<span style="font-size:13px;font-weight:600;color:{MUTED}"> · {len(sec["items"])}</span></div>')
    # raggruppa per sottosezione (per i creator: per creator); i gruppi seguono la loro notizia
    # migliore (gli item arrivano già ordinati per importanza)
    groups: dict[str, list[dict]] = {}
    for it in sec["items"]:
        groups.setdefault(it.get("subsection") or "", []).append(it)
    pos = {id(it): n for n, it in enumerate(sec["items"])}
    keys = sorted(groups, key=lambda k: min(pos[id(i)] for i in groups[k]))
    body = ""
    for k in keys:
        label = groups[k][0].get("subsection_label") or ""
        if label and len(keys) > 1:
            body += (f'<div style="{EYEBROW};color:{accent};padding:12px 0 0;border-top:1px solid {LINE}">'
                     f'{escape(label)}</div>')
            body += "".join(_item(it, day, pick_labels) for it in groups[k]).replace(
                f"border-top:1px solid {LINE}", "border-top:0", 1)
        else:
            body += "".join(_item(it, day, pick_labels) for it in groups[k])
    return (f'<div style="background:{CARD};border-radius:14px;border-top:4px solid {accent};'
            f'padding:18px 22px 6px;margin:0 0 16px">{head}{body}</div>')


def _pick_block(kind: str, pk: dict, day: str) -> str:
    is_post = kind == "linkedin"
    label = "💼 Post LinkedIn del giorno" if is_post else "🎬 Short del giorno"
    cta = "Apri nell'app e genera il post" if is_post else "Apri nell'app e genera lo script"
    rows = ""
    if is_post and pk.get("target"):
        rows += f'<div style="margin:0 0 6px"><b>A chi parla.</b> {escape(pk["target"])}</div>'
    if is_post and pk.get("pain"):
        rows += f'<div style="margin:0 0 6px"><b>Il problema.</b> {escape(pk["pain"])}</div>'
    if is_post and pk.get("angle"):
        rows += f'<div style="margin:0 0 6px"><b>L\'angolo.</b> {escape(pk["angle"])}</div>'
    rows += f'<div style="margin:0 0 6px"><b>Perché oggi.</b> {escape(pk["why"])}</div>'
    if pk.get("caveat"):
        rows += (f'<div style="margin:8px 0 0;padding:8px 10px;border-radius:8px;background:#fcefd6;'
                 f'color:#855000"><b>Prima di pubblicare.</b> {escape(pk["caveat"])}</div>')
    alts = ""
    if pk.get("alternatives"):
        alts = (f'<div style="font-size:12.5px;color:{MUTED};margin:12px 0 0">In alternativa: '
                + " · ".join(f'<a href="{app_link(day, a["item_id"])}" style="color:{MUTED}">'
                             f'{escape(a["title"])}</a>' for a in pk["alternatives"]) + '</div>')
    return (
        f'<div style="padding:16px 0;border-top:1px solid {LINE}">'
        f'<div style="{EYEBROW};color:{BLUE};margin:0 0 8px">{label}'
        f'<span style="color:{MUTED};font-weight:700"> · adatta {pk["score"]}/10</span>'
        f' &nbsp;{_badge(pk["badge"])}</div>'
        f'<div style="font-size:18px;line-height:1.3;font-weight:800;margin:0 0 10px">'
        f'<a href="{app_link(day, pk["item_id"])}" style="color:{INK};text-decoration:none">{escape(pk["title"])}</a></div>'
        f'<div style="font-size:16px;line-height:1.5;font-style:italic;background:{YELLOW_SOFT};'
        f'border-radius:8px;padding:10px 14px;margin:0 0 12px">«{escape(pk["hook"])}»</div>'
        f'<div style="font-size:14.5px;line-height:1.55;color:{INK}">{rows}</div>'
        f'<div style="margin:14px 0 0"><a href="{app_link(day, pk["item_id"])}" style="display:inline-block;'
        f'background:{BLUE};color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;'
        f'padding:9px 16px;border-radius:9px">{cta}&nbsp;→</a></div>{alts}</div>')


def _picks(r: dict) -> str:
    if "picks" not in r:   # report fatti prima che esistessero le scelte del giorno
        return ""
    picks, day = r.get("picks") or {}, r["date"]
    body = "".join(_pick_block(k, picks[k], day) for k in ("linkedin", "short") if picks.get(k))
    if not picks.get("linkedin") and r["stats"]["stories"]:
        body = (f'<div style="padding:12px 0 6px;border-top:1px solid {LINE};font-size:14.5px;line-height:1.55;'
                f'color:{MUTED}"><b style="color:{INK}">💼 Oggi nessun post LinkedIn.</b> Nessuna notizia è '
                f'abbastanza forte per la tua nicchia: meglio saltare un giorno che forzare.</div>') + body
    if not body:
        return ""
    return (f'<div style="background:{CARD};border-radius:14px;border-top:4px solid {BLUE};'
            f'padding:18px 22px 8px;margin:0 0 16px">'
            f'<div style="font-size:13px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;'
            f'padding:0 0 12px">Da pubblicare oggi</div>{body}</div>')


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
    return f"<div><b>Controlli di oggi.</b> {escape(' · '.join(bits))}.</div>"


def to_html(r: dict) -> str:
    s, day = r["stats"], r["date"]
    picks = r.get("picks") or {}
    pick_labels: dict[str, list[str]] = {}
    for key, label in (("linkedin", "Post LinkedIn del giorno"), ("short", "Short del giorno")):
        if picks.get(key):
            pick_labels.setdefault(picks[key]["item_id"], []).append(label)

    breve = "".join(
        f'<tr><td style="vertical-align:top;padding:0 12px 10px 0;font-size:13px;font-weight:800;'
        f'color:{YELLOW};white-space:nowrap">0{n}</td>'
        f'<td style="vertical-align:top;padding:0 0 10px;font-size:15.5px;line-height:1.5;color:#ffffff">'
        f'{escape(x)}</td></tr>' for n, x in enumerate(r["in_breve"], 1))
    full = [sec for sec in r["sections"] if sec["items"]]
    empty = [sec["title"] for sec in r["sections"] if not sec["items"]]
    chips = "".join(
        f'<span style="display:inline-block;font-size:12px;font-weight:700;color:{INK};background:{CARD};'
        f'border-radius:12px;padding:3px 10px;margin:0 6px 6px 0"><span style="color:{ACCENT.get(sec["id"], INK)}">●</span> '
        f'{escape(sec["title"].split(":")[0])} {len(sec["items"])}</span>' for sec in full)
    notes = []
    if empty:
        notes.append("Nessuna novità rilevante oggi in: " + ", ".join(t.split(":")[0] for t in empty) + ".")
    if s.get("source_errors"):
        notes.append("Fonti non raggiungibili oggi: " + ", ".join(e["source"] for e in s["source_errors"]) + ".")
    if s.get("dropped_broken_links"):
        notes.append(f"Notizie scartate per link non funzionante: {len(s['dropped_broken_links'])}.")
    footer_notes = "".join(f"<div>{escape(n)}</div>" for n in notes)
    d = date.fromisoformat(day)

    html = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(r['title'])} — {day}</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:{FONT};color:{INK}">
<div style="max-width:680px;margin:0 auto;padding:22px 12px">
<div style="padding:4px 10px 18px">
<div style="{EYEBROW};color:{BLUE}">Report AI <span style="color:{MUTED}">· {d.year}</span></div>
<div style="font-size:34px;line-height:1.1;font-weight:800;letter-spacing:-.02em;margin:6px 0 8px">
{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]}</div>
<div style="font-size:14px;color:{MUTED};margin:0 0 12px"><b style="color:{INK}">{s['stories']} notizie</b>
 · circa {r['reading_minutes']} minuti · {s['collected']} elementi raccolti, {s['discarded']} scartati come rumore
 · <a href="{app_link(day)}" style="color:{BLUE};font-weight:700;text-decoration:none">Apri nell'app&nbsp;→</a></div>
<div>{chips}</div>
</div>
{f'''<div style="background:{INK};border-radius:14px;padding:18px 22px 8px;margin:0 0 16px">
<div style="{EYEBROW};color:#ffffff;opacity:.7;margin:0 0 12px">In breve</div>
<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{breve}</table>
</div>''' if r["in_breve"] else ""}
{_picks(r)}
{''.join(_section(sec, day, pick_labels) for sec in full)}
<div style="font-size:12.5px;color:{MUTED};line-height:1.7;padding:6px 10px 26px">
{_checks(s)}
{footer_notes}
<div><b>Badge.</b> ✅ fonte ufficiale · 🔁 confermata da più fonti indipendenti · ⚠️ una sola fonte non
ufficiale · 📦 descrizione del progetto, non ancora provato · ❌ smentita da una fonte ufficiale.</div>
<div>Generato con Claude ({escape(s.get('model') or '')}) alle {r['generated_at'][11:16]} UTC.</div>
</div>
</div></body></html>"""
    return re.sub(r">\s+<", "><", html)

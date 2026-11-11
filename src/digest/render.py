"""Fase 3 — il report in HTML, pensato per Gmail (desktop e telefono).

Regole per le email: stili inline (Gmail ignora molto del CSS in <head>), niente JavaScript,
larghezza massima 680px, e HTML compatto: Gmail taglia i messaggi oltre ~102 KB.
"""

import re
from datetime import date
from html import escape

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]

BADGES = {  # etichetta, testo, sfondo
    "ufficiale": ("✅ Ufficiale", "#1d6b3a", "#e6f4ea"),
    "confermata": ("🔁 Confermata", "#1a4f8b", "#e5effa"),
    "da_verificare": ("⚠️ Da verificare", "#8a5300", "#fdf1dc"),
    "smentita": ("❌ Smentita", "#a12020", "#fbe6e6"),
    "dal_repo": ("📦 Dal README", "#4b4f58", "#eceef1"),
}
ACCENT = {"claude": "#c96442", "higgsfield": "#6d4aff", "elevenlabs": "#1f1f1f",
          "creators": "#d0344e", "github": "#2b3137"}

INK, MUTED, LINE, BG, CARD = "#1f2328", "#5f6670", "#e4e7eb", "#f4f5f7", "#ffffff"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def data_italiana(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{GIORNI[d.weekday()].capitalize()} {d.day} {MESI[d.month - 1]} {d.year}"


def _a(url: str, text: str, style: str = "") -> str:
    return f'<a href="{escape(url, quote=True)}" style="color:{INK};{style}">{escape(text)}</a>'


def _badge(key: str) -> str:
    label, fg, bg = BADGES.get(key, BADGES["da_verificare"])
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            f'background:{bg};color:{fg};font-size:12px;font-weight:600">{label}</span>')


def _item(it: dict) -> str:
    sources = " · ".join(
        f'<a href="{escape(s["url"], quote=True)}" style="color:{MUTED}">{escape(s["name"])}</a>'
        for s in it["sources"])
    return (
        f'<div style="padding:16px 0;border-top:1px solid {LINE}">'
        f'<div style="font-size:17px;line-height:1.35;font-weight:700;margin:0 0 6px">'
        f'{_a(it["primary_url"], it["title"], "text-decoration:none")}</div>'
        f'<div style="margin:0 0 8px">{_badge(it["badge"])}'
        f'<span style="color:{MUTED};font-size:12px"> {escape(it["badge_note"])}</span></div>'
        f'<div style="font-size:15px;line-height:1.55;color:{INK};margin:0 0 8px">{escape(it["summary"])}</div>'
        + (f'<ul style="margin:0 0 10px;padding:0 0 0 20px;font-size:14px;line-height:1.5;color:{INK}">'
           + "".join(f'<li style="margin:0 0 3px">{escape(p)}</li>' for p in it.get("key_points", []))
           + '</ul>' if it.get("key_points") else "") +
        f'<div style="font-size:14px;line-height:1.5;color:{INK};background:{BG};border-radius:6px;'
        f'padding:8px 10px;margin:0 0 8px"><b>Perché ti serve:</b> {escape(it["why"])}</div>'
        f'<div style="font-size:12px;color:{MUTED}">Fonti: {sources}</div>'
        f'</div>')


def _section(sec: dict) -> str:
    accent = ACCENT.get(sec["id"], INK)
    head = (f'<div style="font-size:20px;font-weight:800;color:{INK};padding:0 0 6px;'
            f'border-bottom:3px solid {accent}">{escape(sec["title"])}'
            f'<span style="font-size:13px;font-weight:600;color:{MUTED}"> · {len(sec["items"])}</span></div>')
    if not sec["items"]:
        body = f'<p style="color:{MUTED};font-size:14px;margin:12px 0 0">Nessuna novità rilevante.</p>'
    else:
        # raggruppa per sottosezione (per i creator: per creator)
        groups: dict[str, list[dict]] = {}
        for it in sec["items"]:
            groups.setdefault(it.get("subsection") or "", []).append(it)
        # i gruppi seguono la loro notizia migliore (gli item arrivano già ordinati per importanza
        # e, a parità, per priorità decisa in selezione)
        pos = {id(it): n for n, it in enumerate(sec["items"])}
        keys = sorted(groups, key=lambda k: min(pos[id(i)] for i in groups[k]))
        body = ""
        for k in keys:
            label = groups[k][0].get("subsection_label") or ""
            if label and len(keys) > 1:
                body += (f'<div style="font-size:12px;font-weight:700;letter-spacing:.06em;'
                         f'text-transform:uppercase;color:{accent};margin:14px 0 0">{escape(label)}</div>')
            body += "".join(_item(it) for it in groups[k])
    return (f'<div style="background:{CARD};border-radius:10px;padding:18px 20px;margin:0 0 16px">'
            f'{head}{body}</div>')


def to_html(r: dict) -> str:
    s = r["stats"]
    breve = "".join(f'<li style="margin:0 0 6px">{escape(x)}</li>' for x in r["in_breve"])
    indice = " · ".join(f'{escape(sec["title"])} ({len(sec["items"])})' for sec in r["sections"])
    notes = []
    if s.get("source_errors"):
        notes.append("Fonti non raggiungibili oggi: " + ", ".join(e["source"] for e in s["source_errors"]))
    if s.get("dropped_broken_links"):
        notes.append(f"Notizie scartate per link non funzionante: {len(s['dropped_broken_links'])}")
    footer_notes = "".join(f"<div>{escape(n)}</div>" for n in notes)

    html = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(r['title'])} — {r['date']}</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:{FONT};color:{INK}">
<div style="max-width:680px;margin:0 auto;padding:20px 12px">
<div style="padding:4px 8px 16px">
<div style="font-size:13px;color:{MUTED}">{data_italiana(r['date'])}</div>
<div style="font-size:24px;line-height:1.25;font-weight:800;margin:4px 0 6px">{escape(r['title'])}</div>
<div style="font-size:13px;color:{MUTED}">{s['stories']} notizie · circa {r['reading_minutes']} minuti
 · {s['collected']} elementi raccolti, {s['discarded']} scartati come rumore</div>
</div>
<div style="background:{INK};color:#fff;border-radius:10px;padding:16px 20px;margin:0 0 16px">
<div style="font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;opacity:.75;margin:0 0 8px">In breve</div>
<ul style="margin:0;padding:0 0 0 18px;font-size:15px;line-height:1.5">{breve}</ul>
<div style="font-size:12px;opacity:.7;margin:10px 0 0">{indice}</div>
</div>
{''.join(_section(sec) for sec in r['sections'])}
<div style="font-size:12px;color:{MUTED};line-height:1.6;padding:4px 8px 24px">
{footer_notes}
<div>Badge: ✅ fonte ufficiale · 🔁 confermata da più fonti · ⚠️ una sola fonte non ufficiale ·
📦 descrizione del progetto, non ancora provato · ❌ smentita.</div>
<div>Generato automaticamente con Claude ({escape(s.get('model') or '')}) alle {r['generated_at'][11:16]} UTC.</div>
</div>
</div></body></html>"""
    return re.sub(r">\s+<", "><", html)

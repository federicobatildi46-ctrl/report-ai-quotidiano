"""Fase 3 — invio del report via Gmail (SMTP con "password per le app"), da te a te.

Gratis, funziona uguale sul PC e su GitHub Actions. Servono in .env (o nei Secrets del repo):
GMAIL_ADDRESS, GMAIL_APP_PASSWORD e, facoltativo, REPORT_TO (default: lo stesso indirizzo).
"""

import json
import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from digest import REPORTS_DIR
from digest.build import to_markdown, write_html
from digest.render import MESI

# Porta 587 + STARTTLS: sulla 465 Avast (Mail Shield) intercetta la connessione con un certificato
# "Untrusted Root" che giustamente viene rifiutato; la 587 passa con verifica completa.
GMAIL_SMTP = ("smtp.gmail.com", 587)
GMAIL_CLIP_BYTES = 102_000   # oltre, Gmail mostra "[Messaggio troncato]"


class SendError(RuntimeError):
    pass


def latest_report() -> Path:
    files = sorted(REPORTS_DIR.glob("????-??-??.json"))
    if not files:
        raise FileNotFoundError("nessun report in reports/: esegui prima `digest build`")
    return files[-1]


def build_message(report_path: Path, sender: str, to: str) -> EmailMessage:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    html = write_html(report_path).read_text(encoding="utf-8")   # sempre con l'ultimo layout

    d = date.fromisoformat(report["date"])
    msg = EmailMessage()
    msg["Subject"] = f"Report AI {d.day} {MESI[d.month - 1]} {d.year}"   # es. "Report AI 11 novembre 2026"
    msg["From"] = formataddr(("Report AI", sender))
    msg["To"] = to
    msg.set_content(to_markdown(report))          # versione testo, per client senza HTML
    msg.add_alternative(html, subtype="html")
    if len(html.encode("utf-8")) > GMAIL_CLIP_BYTES:
        print(f"Attenzione: HTML di {len(html) // 1024} KB, Gmail potrebbe troncarlo.")
    return msg


def send(report_path: Path | None = None, to: str | None = None) -> tuple[Path, str]:
    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    to = (to or os.getenv("REPORT_TO", "") or sender).strip()
    if not sender or not password:
        raise SendError("mancano GMAIL_ADDRESS e/o GMAIL_APP_PASSWORD in .env "
                        "(vedi DOMANDE_APERTE.md, Fase 3)")
    report_path = report_path or latest_report()
    msg = build_message(report_path, sender, to)
    try:
        with smtplib.SMTP(*GMAIL_SMTP, timeout=60) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(sender, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise SendError("Gmail ha rifiutato l'accesso: controlla GMAIL_ADDRESS e la password per "
                        f"le app (16 lettere, non la password normale). Dettaglio: {e.smtp_code}") from None
    return report_path, to


def send_alert(reason: str, run_url: str = "") -> str:
    """Email breve da te a te quando il report del mattino NON è partito, con il motivo."""
    from datetime import UTC, datetime

    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    to = (os.getenv("REPORT_TO", "") or sender).strip()
    if not sender or not password:
        raise SendError("mancano GMAIL_ADDRESS e/o GMAIL_APP_PASSWORD")
    d = datetime.now(UTC).date()
    msg = EmailMessage()
    msg["Subject"] = f"⚠️ Report AI {d.day} {MESI[d.month - 1]} {d.year}: non è partito"
    msg["From"] = formataddr(("Report AI", sender))
    msg["To"] = to
    msg.set_content(
        "Il report di stamattina non è stato inviato.\n\n"
        f"Motivo (ultime righe del log):\n{reason.strip() or '(nessun dettaglio)'}\n\n"
        "Cosa succede adesso: il sistema riprova da solo (routine delle 07:30, l'app sul PC ogni 10 "
        "minuti, i controlli di GitHub). Le notizie non vanno perse: il prossimo report riparte "
        "dall'ultimo riuscito.\n\n"
        "Per rilanciarlo subito: GitHub → Actions → \"Report AI quotidiano\" → Run workflow, "
        "oppure apri l'app e premi \"Controlla ora\".\n"
        + (f"\nDettagli dell'esecuzione: {run_url}\n" if run_url else "")
        + "\nRiceverai al massimo un avviso al giorno.")
    with smtplib.SMTP(*GMAIL_SMTP, timeout=60) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(sender, password)
        smtp.send_message(msg)
    return to


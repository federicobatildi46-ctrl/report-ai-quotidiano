"""Riga di comando: `uv run digest <comando>`."""

import argparse
import asyncio
import sys

import httpx
from dotenv import load_dotenv

from digest import ROOT
from digest.sources import check_url, iter_sources
from digest.web import make_client


async def _check_all() -> int:
    targets = [(section, src, check_url(src)) for section, src in iter_sources()]

    async def check(client, url):
        if url is None:
            return "via Apify", True
        try:
            r = await client.get(url)
            return str(r.status_code), r.status_code == 200
        except httpx.HTTPError as e:
            return type(e).__name__, False

    async with make_client() as client:
        results = await asyncio.gather(*(check(client, url) for _, _, url in targets))
    failed = 0
    for (section, src, _), (status, ok) in zip(targets, results):
        failed += not ok
        print(f"{'OK ' if ok else 'ERR'}  [{section:<10}] {src['name']:<48} {status}")
    print(f"\n{len(results) - failed}/{len(results)} fonti raggiungibili.")
    return 1 if failed else 0


def _collect(args) -> int:
    from digest.collect import collect

    out, payload = asyncio.run(collect(hours=args.hours, dry_run=args.dry_run, only=args.only))
    print(f"Finestra: ultime {payload['lookback_hours']} ore (dal {payload['since'][:16]} UTC)\n")
    errors = 0
    for s in payload["stats"]:
        flag = "ERR" if s["error"] else ("1a " if s["baseline"] else "OK ")
        extra = s["error"] or ("prima esecuzione: fonte memorizzata" if s["baseline"] else "")
        print(f"{flag} [{s['section']:<10}] {s['source']:<30} {s['new']:>3} nuovi  {s['secs']:>5}s  {extra}")
        errors += bool(s["error"])
    print(f"\n{len(payload['items'])} elementi salvati in {out.relative_to(ROOT)}"
          f"{'  (prova: memoria NON aggiornata)' if args.dry_run else ''}")
    return 1 if errors else 0


def _build(args) -> int:
    from pathlib import Path

    from digest.build import build

    out, r = build(Path(args.input) if args.input else None, model=args.model)
    s = r["stats"]
    print(f"Report: {out.relative_to(ROOT)}  (+ anteprima .md)")
    print(f"{s['stories']} notizie da {s['collected']} elementi · {s['discarded']} scartati come rumore"
          f" · ~{r['reading_minutes']} min di lettura")
    for sec in r["sections"]:
        print(f"  {sec['title']:<42} {len(sec['items'])}")
    if s["dropped_broken_links"]:
        print(f"Scartate per link rotto: {len(s['dropped_broken_links'])}")
    for phase, st in s["claude"].items():
        if st:
            print(f"Claude {phase}: {st['secs']}s · token nuovi {st['input_tokens']} "
                  f"(+{st.get('cache_read_tokens', 0)} da cache) · scritti {st['output_tokens']} · "
                  f"turni {st.get('turns')}")
    return 0


def _render(args) -> int:
    from pathlib import Path

    from digest.build import write_html
    from digest.send import latest_report

    out = write_html(Path(args.report) if args.report else latest_report())
    print(f"HTML: {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    return 0


def _send(args) -> int:
    from pathlib import Path

    from digest.send import SendError, send

    try:
        path, to = send(Path(args.report) if args.report else None, to=args.to)
    except SendError as e:
        print(f"Invio non riuscito: {e}")
        return 1
    print(f"Inviato {path.name} a {to}")
    return 0


def _daily(args) -> int:
    """Il giro completo del mattino: raccolta → report → email → memoria aggiornata."""
    from digest.build import build
    from digest.collect import collect
    from digest.send import SendError, send
    from digest.state import SeenState

    state = SeenState.load()
    raw_path, payload = asyncio.run(collect(state=state))
    errors = [s["source"] for s in payload["stats"] if s["error"]]
    videos = [i for i in payload["items"] if i["kind"] in ("video", "short")]
    print(f"Raccolta: {len(payload['items'])} elementi"
          + (f" · fonti in errore: {', '.join(errors)}" if errors else "")
          + f" · video con trascrizione: {sum(bool(v['meta'].get('transcript')) for v in videos)}/{len(videos)}")

    report_path, report = build(raw_path)
    print(f"Report: {report['stats']['stories']} notizie · ~{report['reading_minutes']} min")

    if args.no_send:
        print("Invio saltato (--no-send)")
    else:
        try:
            _, to = send(report_path)
            print(f"Email inviata a {to}")
        except SendError as e:
            print(f"Invio non riuscito: {e}")
            return 1

    state.save()   # solo ora: se qualcosa fallisce prima, domani le notizie non vanno perse
    print("Memoria aggiornata (data/seen.json)")
    return 0


def _serve(args) -> int:
    import os
    import threading
    import webbrowser

    import uvicorn

    port = args.port or int(os.getenv("DIGEST_PORT", "8787"))
    url = f"http://localhost:{port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"App su {url}  (chiudi questa finestra o Ctrl+C per fermarla)")
    uvicorn.run("digest.app:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(prog="digest", description="Report AI quotidiano")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-sources", help="verifica che tutte le fonti rispondano")
    p = sub.add_parser("collect", help="raccoglie le novità da tutte le fonti")
    p.add_argument("--hours", type=int, help="finestra in ore (default: lookback_hours di topics.yaml)")
    p.add_argument("--dry-run", action="store_true", help="non aggiorna data/seen.json")
    p.add_argument("--only", nargs="+", metavar="ID", help="solo queste fonti (id di sources.yaml)")
    p = sub.add_parser("build", help="Claude seleziona, scrive e verifica → reports/AAAA-MM-GG.json")
    p.add_argument("--input", help="file di raccolta (default: l'ultimo in data/raw)")
    p.add_argument("--model", help="modello Claude (default: report.model di topics.yaml)")
    p = sub.add_parser("render", help="rigenera l'HTML di un report")
    p.add_argument("--report", help="file JSON del report (default: l'ultimo in reports/)")
    p = sub.add_parser("send", help="invia il report via Gmail")
    p.add_argument("--report", help="file JSON del report (default: l'ultimo in reports/)")
    p.add_argument("--to", help="destinatario (default: REPORT_TO o GMAIL_ADDRESS)")
    p = sub.add_parser("daily", help="giro completo: collect + build + send (quello del cloud)")
    p.add_argument("--no-send", action="store_true", help="non inviare l'email")
    p = sub.add_parser("serve", help="app locale con report, archivio e generatori")
    p.add_argument("--port", type=int, help="porta (default: DIGEST_PORT o 8787)")
    p.add_argument("--no-browser", action="store_true", help="non aprire il browser")
    args = parser.parse_args()

    if args.cmd == "check-sources":
        sys.exit(asyncio.run(_check_all()))
    if args.cmd == "collect":
        sys.exit(_collect(args))
    if args.cmd == "build":
        sys.exit(_build(args))
    if args.cmd == "render":
        sys.exit(_render(args))
    if args.cmd == "send":
        sys.exit(_send(args))
    if args.cmd == "daily":
        sys.exit(_daily(args))
    if args.cmd == "serve":
        sys.exit(_serve(args))

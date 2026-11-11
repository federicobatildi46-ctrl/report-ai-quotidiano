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
    for name, phase in [("send", 3), ("daily", 4), ("serve", 5)]:
        sub.add_parser(name, help=f"(Fase {phase}, non ancora implementato)")
    args = parser.parse_args()

    if args.cmd == "check-sources":
        sys.exit(asyncio.run(_check_all()))
    if args.cmd == "collect":
        sys.exit(_collect(args))
    if args.cmd == "build":
        sys.exit(_build(args))
    print(f"'{args.cmd}' non è ancora implementato: vedi PIANO_OPERATIVO.md, §6.")
    sys.exit(2)

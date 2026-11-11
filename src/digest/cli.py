"""Riga di comando: `uv run digest <comando>`."""

import argparse
import asyncio
import sys

import httpx

from digest.sources import Endpoint, endpoints

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) digest-local/0.1"


async def _check(client: httpx.AsyncClient, ep: Endpoint) -> tuple[Endpoint, str, bool]:
    if ep.type == "apify":
        return ep, "via Apify (Fase 1)", True
    try:
        r = await client.get(ep.url)
        return ep, f"{r.status_code}", r.status_code == 200
    except httpx.HTTPError as e:
        return ep, type(e).__name__, False


async def _check_all() -> int:
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True,
                                 timeout=20) as client:
        results = await asyncio.gather(*(_check(client, ep) for ep in endpoints()))
    failed = 0
    for ep, status, ok in results:
        failed += not ok
        print(f"{'OK ' if ok else 'ERR'}  [{ep.section:<10}] {ep.name:<45} {status}")
    print(f"\n{len(results) - failed}/{len(results)} fonti raggiungibili.")
    return 1 if failed else 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="digest", description="Report AI quotidiano")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-sources", help="verifica che tutte le fonti rispondano")
    for name, phase in [("collect", 1), ("build", 2), ("serve", 3), ("daily", 4)]:
        sub.add_parser(name, help=f"(Fase {phase}, non ancora implementato)")
    args = parser.parse_args()

    if args.cmd == "check-sources":
        sys.exit(asyncio.run(_check_all()))
    print(f"'{args.cmd}' non è ancora implementato: vedi PIANO_OPERATIVO.md, §6.")
    sys.exit(2)

"""Fase 1 — raccolta: interroga tutte le fonti e salva le novità in data/raw/items-AAAA-MM-GG.json."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from digest import CONFIG_DIR, DATA_DIR
from digest.collectors import COLLECTORS
from digest.collectors.base import Ctx
from digest.sources import iter_sources, load_config
from digest.state import SeenState
from digest.web import make_client, to_json

RAW_DIR = DATA_DIR / "raw"
SOURCE_TIMEOUT = 360  # secondi: una fonte lenta non blocca le altre


def default_lookback() -> int:
    with open(CONFIG_DIR / "topics.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["report"]["lookback_hours"]


async def _run_source(ctx: Ctx) -> dict:
    t0 = time.perf_counter()
    try:
        fn = COLLECTORS[ctx.src["type"]]
        items = await asyncio.wait_for(fn(ctx), SOURCE_TIMEOUT)
        return {"ctx": ctx, "items": items, "error": None, "secs": time.perf_counter() - t0}
    except Exception as e:  # una fonte rotta non deve fermare il report
        msg = f"{type(e).__name__}: {e}"[:300]
        return {"ctx": ctx, "items": [], "error": msg, "secs": time.perf_counter() - t0}


async def collect(hours: int | None = None, dry_run: bool = False,
                  only: list[str] | None = None,
                  state: SeenState | None = None) -> tuple[Path, dict]:
    """Con `state` passato dal chiamante la memoria NON viene salvata qui: la salva lui
    (es. `daily` la salva solo dopo che report e invio sono riusciti)."""
    caller_saves = state is not None
    hours = hours or default_lookback()
    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)
    state = state or SeenState.load()

    async with make_client() as client:
        ctxs = [Ctx(client=client, src=src, section=section, since=since, state=state)
                for section, src in iter_sources(load_config())
                if not only or src["id"] in only]
        results = await asyncio.gather(*(_run_source(c) for c in ctxs))

    items, report = [], []
    for res in results:
        ctx = res["ctx"]
        baseline = not ctx.initialized
        if res["error"] is None:
            state.commit(ctx.id, ctx.remembered)   # memoria aggiornata solo se la fonte è andata
            items.extend(res["items"])
        report.append({"source": ctx.id, "section": ctx.section, "new": len(res["items"]),
                       "baseline": baseline,
                       "error": res["error"], "secs": round(res["secs"], 1)})

    payload = {
        "generated_at": now.isoformat(),
        "since": since.isoformat(),
        "lookback_hours": hours,
        "stats": report,
        "items": [i.to_dict() for i in items],
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"items-{now.date().isoformat()}.json"
    out.write_text(to_json(payload), encoding="utf-8")
    if not dry_run and not caller_saves:
        state.save()
    return out, payload

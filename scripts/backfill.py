#!/usr/bin/env python3
"""
backfill.py — одноразовий добір всієї доступної історії каналу.

Відмінність від collect.py:
  • ігнорує cursor (min_id=0)
  • limit = --max (default 3000)
  • після завершення cursor ставиться на останнє повідомлення

Використання:
    python scripts/backfill.py --channels ukrainska_pravda_fast --max 2000
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.collector import run_collect
from collector.config import Config
from collector.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill: одноразовий добір всієї історії")
    p.add_argument("--channels", "-c", required=True,
                   help="Список каналів через кому")
    p.add_argument("--max", "-m", type=int, default=3000,
                   help="Максимум повідомлень на канал (default: 3000)")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    cfg.channels = [c.strip().lstrip("@") for c in args.channels.split(",")]

    db = Database(cfg.db_path)
    print(f"Backfill: {cfg.channels}, max={args.max} на канал")

    result = await run_collect(cfg, db, backfill=True, backfill_limit=args.max)

    print(f"\n✓ Backfill завершено. Нових записів: {result['total_new']}")
    for ch, info in result["channels"].items():
        status = f"+{info['new']}" if info["error"] is None else f"⚠ {info['error'][:80]}"
        print(f"  {ch}: {status}")

    db.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
collect.py — інкрементний збір.

Використання:
    python scripts/collect.py
    python scripts/collect.py --channels ukrainska_pravda_fast,ukrinform_ua
    python scripts/collect.py --channels ukrainska_pravda_fast --batch 50
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Дозволяємо запуск з кореня проєкту
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
    p = argparse.ArgumentParser(description="Інкрементний збір Telegram-каналів")
    p.add_argument(
        "--channels", "-c",
        help="Список каналів через кому (перевизначає TG_CHANNELS у .env)",
    )
    p.add_argument(
        "--batch", "-b", type=int,
        help="Кількість повідомлень за прогін (перевизначає BATCH_SIZE)",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    cfg = Config.from_env()

    if args.channels:
        cfg.channels = [c.strip().lstrip("@") for c in args.channels.split(",")]
    if args.batch:
        cfg.batch_size = args.batch

    db = Database(cfg.db_path)

    result = await run_collect(cfg, db)

    print(f"\n✓ Прогін {result['run_id']} завершено.")
    print(f"  Нових записів: {result['total_new']}")
    for ch, info in result["channels"].items():
        status = f"+{info['new']}" if info["error"] is None else f"⚠ {info['error'][:60]}"
        print(f"  {ch}: {status}")

    db.close()


if __name__ == "__main__":
    asyncio.run(main())

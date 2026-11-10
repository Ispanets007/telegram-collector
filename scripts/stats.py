#!/usr/bin/env python3
"""
stats.py — дашборд статистики збору (термінал).

Використання:
    python scripts/stats.py
    python scripts/stats.py --export sample_data/export.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import Config
from collector.database import Database

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Статистика збору")
    p.add_argument("--export", "-e",
                   help="Експортувати всі записи у JSONL-файл")
    p.add_argument("--source", "-s",
                   help="Фільтр за каналом при експорті")
    return p.parse_args()


def print_stats(stats: dict) -> None:
    if HAS_RICH:
        _print_rich(stats)
    else:
        _print_plain(stats)


def _print_rich(stats: dict) -> None:
    console = Console()
    console.print(f"\n[bold green]Telegram Collector — статистика[/bold green]")
    console.print(f"  Всього записів: [bold]{stats['total']}[/bold]")
    console.print(f"  FloodWait-подій: [yellow]{stats['floodwaits']}[/yellow]\n")

    if stats["by_source"]:
        t = Table(title="По каналах", box=box.SIMPLE)
        t.add_column("Канал", style="cyan")
        t.add_column("Повідомлень", justify="right")
        t.add_column("Cursor (last id)", justify="right")
        t.add_column("Оновлено")

        cursor_map = {r["source"]: r for r in stats["cursors"]}
        for row in stats["by_source"]:
            src = row["source"]
            cur = cursor_map.get(src, {})
            t.add_row(
                src,
                str(row["cnt"]),
                str(cur.get("last_message_id", "—")),
                (cur.get("updated_at", "—") or "—")[:19],
            )
        console.print(t)


def _print_plain(stats: dict) -> None:
    print(f"\nTelegram Collector — статистика")
    print(f"  Всього записів: {stats['total']}")
    print(f"  FloodWait-подій: {stats['floodwaits']}\n")
    print(f"{'Канал':<30} {'Повідомлень':>12} {'Cursor':>12} {'Оновлено'}")
    print("-" * 70)
    cursor_map = {r["source"]: r for r in stats["cursors"]}
    for row in stats["by_source"]:
        src = row["source"]
        cur = cursor_map.get(src, {})
        print(
            f"{src:<30} {row['cnt']:>12} "
            f"{cur.get('last_message_id', '—'):>12} "
            f"{(cur.get('updated_at') or '—')[:19]}"
        )


def main() -> None:
    args = parse_args()
    cfg = Config.from_env()
    db = Database(cfg.db_path)

    stats = db.stats()
    print_stats(stats)

    if args.export:
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        n = db.export_jsonl(out, source=args.source)
        print(f"\n✓ Експортовано {n} записів → {out}")

    db.close()


if __name__ == "__main__":
    main()

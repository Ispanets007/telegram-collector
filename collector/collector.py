"""
collector.py — головний цикл збору.

Один прогін = невелика партія на кожен канал зі списку.
Курсор оновлюється лише після успішного запису → ідемпотентність.
Один збій каналу не валить весь прогін.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from telethon import TelegramClient

from .config import Config
from .database import Database
from .telegram_client import (
    ChannelUnavailable,
    ResolveBudgetExceeded,
    build_client,
    fetch_channel_messages,
)
from .utils import ResolveBudget, polite_sleep

logger = logging.getLogger(__name__)


async def run_collect(
    cfg: Config,
    db: Database,
    *,
    channels: Optional[list[str]] = None,
    backfill: bool = False,
    backfill_limit: int = 3000,
) -> dict:
    """
    Основний цикл збору.

    backfill=True → ігнорує cursor, тягне всю доступну історію (до backfill_limit).
    backfill=False → інкрементний режим, продовжує з cursor.
    """
    run_id = str(uuid.uuid4())[:8]
    targets = channels or cfg.channels
    budget = ResolveBudget(limit_per_day=cfg.resolve_budget_per_day)

    summary: dict[str, dict] = {}
    total_new = 0

    db.log_event(run_id, "start", detail=f"targets={targets} backfill={backfill}")
    logger.info("=== Прогін %s | каналів: %d ===", run_id, len(targets))

    client = build_client(cfg)
    await client.start(phone=cfg.phone)

    try:
        for channel in targets:
            logger.info("── Канал: %s ──", channel)
            summary[channel] = {"new": 0, "error": None}

            try:
                min_id = 0 if backfill else db.get_cursor(channel)
                limit = backfill_limit if backfill else cfg.batch_size

                rows, max_id = await fetch_channel_messages(
                    client,
                    channel,
                    db,
                    budget,
                    min_id=min_id,
                    batch_size=limit,
                    message_delay=cfg.message_delay,
                    run_id=run_id,
                    account_name=cfg.phone,
                )

                # Записуємо у БД
                new_count = db.insert_messages_bulk(rows)
                summary[channel]["new"] = new_count
                total_new += new_count

                # Курсор оновлюємо лише після успішного запису
                if max_id > db.get_cursor(channel):
                    db.set_cursor(channel, max_id)

                logger.info(
                    "%s: зібрано %d, нових %d, cursor→%d",
                    channel, len(rows), new_count, max_id,
                )
                db.log_event(run_id, "finish", source=channel,
                             detail=f"fetched={len(rows)} new={new_count} cursor={max_id}")

            except ResolveBudgetExceeded as exc:
                logger.warning("Пропускаємо %s: %s", channel, exc)
                summary[channel]["error"] = str(exc)
                db.log_event(run_id, "skip", source=channel, detail=str(exc))

            except ChannelUnavailable as exc:
                logger.error("Канал %s недоступний: %s", channel, exc)
                summary[channel]["error"] = str(exc)
                db.log_event(run_id, "error", source=channel, detail=str(exc))

            except Exception as exc:
                # Один збій каналу не валить весь прогін
                logger.exception("Несподівана помилка на %s", channel)
                summary[channel]["error"] = str(exc)
                db.log_event(run_id, "error", source=channel, detail=str(exc))

            finally:
                # Пауза між каналами (politeness)
                await polite_sleep(cfg.channel_delay)

    finally:
        await client.disconnect()

    db.log_event(run_id, "done", detail=f"total_new={total_new}")
    logger.info("=== Прогін %s завершено. Нових записів: %d ===", run_id, total_new)

    return {
        "run_id": run_id,
        "total_new": total_new,
        "channels": summary,
    }

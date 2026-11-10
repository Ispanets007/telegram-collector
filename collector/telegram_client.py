"""
telegram_client.py — ініціалізація Telethon-клієнта з проксі та entity-resolve.

Головний урок лекції: бан за ОБСЯГ resolve, а не частоту.
Вирішення: entity_cache в БД + денний бюджет на акаунт.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
)
from telethon.tl.types import (
    Channel,
    InputPeerChannel,
    PeerChannel,
)

from .config import Config
from .database import Database
from .utils import ResolveBudget, async_backoff, polite_sleep

logger = logging.getLogger(__name__)


class ResolveBudgetExceeded(Exception):
    pass


class ChannelUnavailable(Exception):
    pass


def build_client(cfg: Config) -> TelegramClient:
    """Створює Telethon-клієнт з проксі (якщо задано)."""
    session_path = str(Path("data") / cfg.session_name)

    kwargs: dict = {}
    if cfg.proxy:
        try:
            kwargs["proxy"] = cfg.proxy.as_telethon()
        except ImportError:
            logger.warning("PySocks не встановлено — проксі ігнорується. pip install pysocks")

    client = TelegramClient(
        session_path,
        cfg.api_id,
        cfg.api_hash,
        **kwargs,
    )
    return client


async def resolve_channel(
    client: TelegramClient,
    username: str,
    db: Database,
    budget: ResolveBudget,
    account_name: str = "default",
) -> InputPeerChannel:
    """
    Повертає InputPeerChannel для каналу.
    1. Перевіряємо entity_cache → якщо є, будуємо без мережевого виклику.
    2. Перевіряємо бюджет ДО спроби.
    3. Resolve + кешуємо.
    """
    # Кеш-хіт
    cached = db.get_cached_entity(username)
    if cached:
        peer_id, access_hash = cached
        logger.debug("Entity cache HIT: %s → peer_id=%d", username, peer_id)
        return InputPeerChannel(channel_id=peer_id, access_hash=access_hash)

    # Перевіряємо бюджет ДО запиту
    if not budget.consume(account_name):
        raise ResolveBudgetExceeded(
            f"Акаунт {account_name!r} вичерпав денний resolve-бюджет "
            f"({budget.status(account_name)}). Ціль відкладено."
        )

    logger.info("Resolving %s (бюджет: %s)", username, budget.status(account_name))
    try:
        entity = await client.get_entity(username)
    except (UsernameInvalidError, UsernameNotOccupiedError, ChannelPrivateError) as exc:
        raise ChannelUnavailable(f"Канал {username!r} недоступний: {exc}") from exc

    if not isinstance(entity, Channel):
        raise ChannelUnavailable(f"{username!r} — не канал/супергрупа")

    db.cache_entity(
        url=username,
        peer_id=entity.id,
        access_hash=entity.access_hash,
        title=entity.title,
    )
    logger.info("Resolved та закешовано: %s → id=%d title=%r", username, entity.id, entity.title)
    return InputPeerChannel(channel_id=entity.id, access_hash=entity.access_hash)


async def fetch_channel_messages(
    client: TelegramClient,
    username: str,
    db: Database,
    budget: ResolveBudget,
    *,
    min_id: int = 0,
    batch_size: int = 100,
    message_delay: float = 0.05,
    run_id: str = "run",
    account_name: str = "default",
) -> list[dict]:
    """
    Інкрементно тягне повідомлення з каналу.
    min_id: last_message_id з cursor — беремо лише новіші.
    Повертає список dict у канонічній моделі.
    """
    peer = await resolve_channel(client, username, db, budget, account_name)

    rows: list[dict] = []
    max_seen_id = min_id

    logger.info("Збір %s: min_id=%d batch=%d", username, min_id, batch_size)

    try:
        async for msg in client.iter_messages(
            peer,
            limit=batch_size,
            min_id=min_id,
            reverse=True,   # від старих до нових → cursor рухається вперед
        ):
            if msg.id > max_seen_id:
                max_seen_id = msg.id

            # Автор
            if msg.sender_id:
                sender = msg.sender
                if sender and hasattr(sender, "username") and sender.username:
                    author = f"@{sender.username}"
                elif sender and hasattr(sender, "first_name"):
                    author = sender.first_name or str(msg.sender_id)
                else:
                    author = str(msg.sender_id)
            else:
                author = f"channel:{username}"

            # Медіа
            media_type: Optional[str] = None
            if msg.photo:
                media_type = "photo"
            elif msg.video:
                media_type = "video"
            elif msg.document:
                media_type = "document"
            elif msg.audio:
                media_type = "audio"

            rows.append(
                dict(
                    source=username,
                    message_id=msg.id,
                    author=author,
                    url=f"https://t.me/{username}/{msg.id}",
                    date=msg.date,
                    text=msg.text or msg.message or "",
                    media_type=media_type,
                    media_url=None,
                )
            )
            await polite_sleep(message_delay)

    except FloodWaitError as exc:
        wait = exc.seconds + 5  # +5с запасу
        logger.warning(
            "FloodWait на %s: Telegram просить чекати %ds. Сплю...", username, wait
        )
        db.log_event(run_id, "floodwait", source=username,
                     detail=f"FloodWait {exc.seconds}s")
        await asyncio.sleep(wait)
        # Не кидаємо далі — повертаємо те, що встигли зібрати
        logger.info("FloodWait минув, повертаємо %d зібраних записів", len(rows))

    return rows, max_seen_id

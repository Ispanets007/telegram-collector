"""
utils.py — backoff, пейсинг, resolve-бюджет.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import defaultdict
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


# ── Exponential backoff ───────────────────────────────────────────────────────

async def async_backoff(
    attempt: int,
    base: float = 1.0,
    cap: float = 300.0,
    jitter: bool = True,
) -> None:
    """Чекає 2^attempt * base секунд, максимум cap. Jitter ±25%."""
    delay = min(base * (2 ** attempt), cap)
    if jitter:
        delay *= random.uniform(0.75, 1.25)
    logger.info("Backoff attempt %d: sleeping %.1fs", attempt, delay)
    await asyncio.sleep(delay)


# ── Resolve-бюджет (урок лекції: бан за ОБСЯГ, а не частоту) ─────────────────

class ResolveBudget:
    """
    Денний лічильник resolve-запитів на акаунт.
    Рахуємо ДО спроби — мертві цілі не зливають бюджет.
    """

    def __init__(self, limit_per_day: int = 60) -> None:
        self.limit = limit_per_day
        self._counts: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))

    def used_today(self, account: str) -> int:
        return self._counts[account][date.today()]

    def can_resolve(self, account: str) -> bool:
        return self.used_today(account) < self.limit

    def consume(self, account: str) -> bool:
        """Витрачає 1 одиницю бюджету. Повертає False якщо перевищено."""
        if not self.can_resolve(account):
            return False
        self._counts[account][date.today()] += 1
        return True

    def status(self, account: str) -> str:
        used = self.used_today(account)
        return f"{used}/{self.limit}"


# ── Пейсинг ───────────────────────────────────────────────────────────────────

async def polite_sleep(seconds: float) -> None:
    """Затримка з невеликим jitter (±10%) щоб не виглядати як бот."""
    actual = seconds * random.uniform(0.9, 1.1)
    await asyncio.sleep(actual)

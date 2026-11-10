"""
config.py — завантаження та валідація налаштувань з .env
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Обов'язкова змінна {key!r} не задана. "
            f"Скопіюйте .env.example → .env та заповніть значення."
        )
    return val


@dataclass
class ProxyConfig:
    scheme: str       # socks5 / http
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    @classmethod
    def from_url(cls, url: str) -> "ProxyConfig":
        p = urlparse(url)
        return cls(
            scheme=p.scheme,
            host=p.hostname or "",
            port=p.port or 1080,
            username=p.username or None,
            password=p.password or None,
        )

    def as_telethon(self) -> tuple:
        """Формат для TelegramClient(proxy=...)"""
        import socks  # python-socks / pysocks
        kind = socks.SOCKS5 if self.scheme == "socks5" else socks.HTTP
        return (kind, self.host, self.port, True,
                self.username, self.password)


@dataclass
class Config:
    # Telegram API
    api_id: int
    api_hash: str
    phone: str
    session_name: str

    # Збір
    channels: list[str]
    batch_size: int
    channel_delay: float
    message_delay: float
    resolve_budget_per_day: int

    # Зберігання
    db_path: Path
    media_dir: Optional[Path]

    # Проксі
    proxy: Optional[ProxyConfig]

    @classmethod
    def from_env(cls) -> "Config":
        raw_channels = os.getenv("TG_CHANNELS", "").strip()
        channels = [c.strip().lstrip("@") for c in raw_channels.split(",") if c.strip()]
        if not channels:
            raise EnvironmentError("TG_CHANNELS не задано. Вкажіть хоча б один канал.")

        proxy_url = os.getenv("TG_PROXY", "").strip()
        proxy = ProxyConfig.from_url(proxy_url) if proxy_url else None

        media_dir_str = os.getenv("MEDIA_DIR", "").strip()
        media_dir = Path(media_dir_str) if media_dir_str else None

        db_path = Path(os.getenv("DB_PATH", "./data/collector.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            api_id=int(_require("TG_API_ID")),
            api_hash=_require("TG_API_HASH"),
            phone=_require("TG_PHONE"),
            session_name=os.getenv("TG_SESSION", "collector"),
            channels=channels,
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            channel_delay=float(os.getenv("CHANNEL_DELAY", "2.0")),
            message_delay=float(os.getenv("MESSAGE_DELAY", "0.05")),
            resolve_budget_per_day=int(os.getenv("RESOLVE_BUDGET_PER_DAY", "60")),
            db_path=db_path,
            media_dir=media_dir,
            proxy=proxy,
        )

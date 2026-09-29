from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _int_list_env(name: str, default: str) -> list[int]:
    raw = os.getenv(name, default)
    values: list[int] = []
    for chunk in raw.replace(" ", "").split(","):
        if not chunk:
            continue
        try:
            values.append(int(chunk))
        except ValueError:
            continue
    return values or [int(x) for x in default.replace(" ", "").split(",") if x]


def _pool_size_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1, value)


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
DEFAULT_TZ: str = os.getenv("DEFAULT_TZ", "Europe/Moscow")
DEFAULT_DEADLINE_TIME: str = os.getenv("DEFAULT_DEADLINE_TIME", "23:59")
DEFAULT_REMINDER_OFFSETS: list[int] = _int_list_env("DEFAULT_REMINDER_OFFSETS", "24,6,1")
DIGEST_HOUR: int = int(os.getenv("DIGEST_HOUR", "9"))
DB_PATH: Path = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "bot.db")))

DB_POOL_SIZE: int = _pool_size_env("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW: int = _pool_size_env("DB_MAX_OVERFLOW", 5)
DB_POOL_TIMEOUT: int = _pool_size_env("DB_POOL_TIMEOUT", 30)
DB_CONNECT_TIMEOUT: int = _pool_size_env("DB_CONNECT_TIMEOUT", 10)

MAX_REMINDER_OFFSET_HOURS: int = max(DEFAULT_REMINDER_OFFSETS + [24 * 14])
ALLOWED_REMINDER_OFFSETS: set[int] = set(range(1, 24 * 31 + 1)) | {0}
MAX_TITLE_LENGTH: int = 120
MAX_NOTES_LENGTH: int = 500


def resolve_timezone(name: str | None) -> ZoneInfo:
    candidate = (name or DEFAULT_TZ).strip()
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo(DEFAULT_TZ)


def ensure_dirs() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

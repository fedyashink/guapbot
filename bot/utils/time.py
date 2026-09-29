from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(local: datetime) -> datetime:
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def to_local(value: datetime, tz: timezone) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone(tz)

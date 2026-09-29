from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse, urlunparse

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bot.config import (
    DB_CONNECT_TIMEOUT,
    DB_MAX_OVERFLOW,
    DB_PATH,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    DATABASE_URL,
    ensure_dirs,
)
from bot.models import Base

log = logging.getLogger(__name__)

SYNC_PG_DRIVERS = ("psycopg2", "psycopg", "pg8000", "asyncpg", "psycopg2cffi", "psycopg_c")
ASYNCPG_UNSUPPORTED_PARAMS = {
    "sslmode",
    "channel_binding",
    "target_session_attrs",
    "sslcert",
    "sslkey",
    "sslrootcert",
    "sslinline",
    "gssencmode",
    "krbsrvname",
    "connect_timeout",
    "pooler",
    "pgbouncer",
}


SSL_DISABLED_MODES = {"disable", "allow", "prefer", "off"}


def normalize_database_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("sqlite"):
        return raw
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    elif scheme.startswith("postgresql+"):
        if scheme.split("+", 1)[1] in SYNC_PG_DRIVERS:
            scheme = "postgresql+asyncpg"
    return urlunparse(parsed._replace(scheme=scheme))


def strip_asyncpg_unsupported(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    if not parsed.query:
        return url, {}
    kept: list[tuple[str, str]] = []
    dropped: dict[str, str] = {}
    for pair in parsed.query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        if key in ASYNCPG_UNSUPPORTED_PARAMS:
            dropped[key] = value
            continue
        kept.append((key, value))
    query = "&".join(f"{key}={value}" for key, value in kept)
    return urlunparse(parsed._replace(query=query)), dropped


def ssl_mode_to_context(mode: str):
    if mode.lower() in SSL_DISABLED_MODES:
        return None
    if mode.lower() in {"verify-ca", "verify-full"}:
        import ssl

        return ssl.create_default_context(cafile=os.getenv("DB_SSL_CA_FILE") or None)
    return True


def is_postgres(url: str) -> bool:
    return url.startswith("postgresql+") or url.startswith("postgres")


def is_pooled_endpoint(url: str) -> bool:
    host = (make_url(url).host or "").lower()
    return "-pooler" in host or host.endswith("-pooler.region.aws.neon.tech")


def is_sqlite_file(url: str) -> bool:
    return url.startswith("sqlite") and ":memory:" not in url


def build_engine(url: str):
    url = normalize_database_url(url)
    if not url:
        ensure_dirs()
        url = f"sqlite+aiosqlite:///{DB_PATH}"
        return create_async_engine(url, echo=False, future=True)

    if is_postgres(url):
        clean_url, dropped = strip_asyncpg_unsupported(url)
        connect_args: dict = {
            "timeout": DB_CONNECT_TIMEOUT,
            "command_timeout": DB_POOL_TIMEOUT,
        }
        if "sslmode" in dropped:
            connect_args["ssl"] = ssl_mode_to_context(dropped["sslmode"])
        if "connect_timeout" in dropped:
            try:
                connect_args["timeout"] = int(float(dropped["connect_timeout"]))
            except ValueError:
                pass
        if is_pooled_endpoint(clean_url) or "pgbouncer" in dropped or "pooler" in dropped:
            connect_args["statement_cache_size"] = 0
        pool_kwargs: dict = {
            "pool_pre_ping": True,
            "pool_size": DB_POOL_SIZE,
            "max_overflow": DB_MAX_OVERFLOW,
            "pool_timeout": DB_POOL_TIMEOUT,
        }
        return create_async_engine(
            clean_url,
            echo=False,
            future=True,
            connect_args=connect_args,
            **pool_kwargs,
        )

    connect_args: dict = {}
    if is_sqlite_file(url):
        connect_args["timeout"] = DB_CONNECT_TIMEOUT
    return create_async_engine(
        url,
        echo=False,
        future=True,
        poolclass=NullPool,
        connect_args=connect_args,
    )


DATABASE_URL_NORMALIZED = normalize_database_url(DATABASE_URL)
engine = build_engine(DATABASE_URL_NORMALIZED)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


def describe_backend(url: str = "") -> str:
    normalized = normalize_database_url(url) if url else DATABASE_URL_NORMALIZED
    if not normalized:
        return f"SQLite ({DB_PATH})"
    parsed = make_url(normalized)
    host = parsed.host or "?"
    return f"{parsed.drivername}://{host}/{parsed.database}"


async def init_db(retries: int = 5) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            return
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            delay = min(2 ** attempt, 30)
            log.warning(
                "db init failed (attempt %s/%s): %s — retry in %ss",
                attempt,
                retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Не удалось подключиться к БД: {last_error}")


async def close_db() -> None:
    await engine.dispose()

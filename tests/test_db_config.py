from __future__ import annotations

import inspect

import pytest
from sqlalchemy.dialects.postgresql import asyncpg as apg

from bot.db import (
    build_engine,
    describe_backend,
    is_postgres,
    is_sqlite_file,
    normalize_database_url,
    ssl_mode_to_context,
    strip_asyncpg_unsupported,
)

NEON_URL = (
    "postgresql://user:pass@ep-cool-name.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+psycopg2://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("sqlite+aiosqlite:///data/bot.db", "sqlite+aiosqlite:///data/bot.db"),
        ("", ""),
    ],
)
def test_normalize_scheme(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected


def test_normalize_preserves_credentials_and_query() -> None:
    result = normalize_database_url(NEON_URL)
    assert result.startswith("postgresql+asyncpg://user:pass@ep-cool-name")
    assert "sslmode=require" in result


def test_neon_params_are_stripped() -> None:
    clean, dropped = strip_asyncpg_unsupported(normalize_database_url(NEON_URL))
    assert "sslmode" not in clean
    assert "channel_binding" not in clean
    assert dropped["sslmode"] == "require"
    assert dropped["channel_binding"] == "require"


def test_pooler_param_is_stripped() -> None:
    clean, dropped = strip_asyncpg_unsupported(
        normalize_database_url("postgresql://u:p@h/db?pooler=transaction")
    )
    assert "pooler" not in clean
    assert dropped["pooler"] == "transaction"


def test_no_unsupported_params_reach_asyncpg() -> None:
    import asyncpg

    valid = set(inspect.signature(asyncpg.connect).parameters)
    url = normalize_database_url(NEON_URL + "&pooler=transaction&connect_timeout=5")
    engine = build_engine(url)
    _, options = apg.PGDialect_asyncpg().create_connect_args(engine.url)
    leaked = {key for key in options if key not in valid}
    assert leaked == set()


def test_ssl_mode_translation() -> None:
    assert ssl_mode_to_context("require") is True
    assert ssl_mode_to_context("prefer") is None
    assert ssl_mode_to_context("disable") is None
    assert ssl_mode_to_context("allow") is None


def test_neon_engine_enables_tls() -> None:
    engine = build_engine(normalize_database_url(NEON_URL))
    assert engine.dialect.create_connect_args is not None
    assert is_postgres(engine.url.render_as_string(hide_password=False))


def test_postgres_engine_uses_pre_ping() -> None:
    engine = build_engine(normalize_database_url(NEON_URL))
    assert engine.pool._pre_ping is True


def test_sqlite_fallback_uses_local_file() -> None:
    engine = build_engine("")
    assert engine.url.get_backend_name() == "sqlite"
    assert not is_postgres(str(engine.url))


def test_is_sqlite_file_distinguishes_memory() -> None:
    assert is_sqlite_file("sqlite+aiosqlite:///data/bot.db")
    assert not is_sqlite_file("sqlite+aiosqlite:///:memory:")


def test_in_memory_sqlite_has_no_timeout_arg() -> None:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    args = engine.dialect.create_connect_args(engine.url)[1]
    assert "timeout" not in args


def test_build_engine_normalizes_scheme_itself() -> None:
    # Регрессия: сырой postgresql:// без нормализации уходил в диалект psycopg
    engine = build_engine("postgresql://u:p@h/db")
    assert engine.dialect.driver == "asyncpg"


def test_sqlite_url_is_left_alone() -> None:
    engine = build_engine("sqlite+aiosqlite:///data/bot.db")
    assert engine.url.get_backend_name() == "sqlite"


def test_describe_backend_hides_credentials() -> None:
    described = describe_backend("postgresql://u:SuperSecret123@ep-x.aws.neon.tech/db")
    assert "SuperSecret123" not in described
    assert "u:" not in described
    assert "ep-x.aws.neon.tech/db" in described


def test_describe_backend_defaults_to_sqlite() -> None:
    assert describe_backend("").startswith("SQLite")


def _dbapi_args(url: str) -> dict:
    engine = build_engine(url)
    creator = engine.sync_engine.pool._creator
    for cell in creator.__closure__ or ():
        value = cell.cell_contents
        if isinstance(value, dict):
            return value
    return {}


def test_pooled_neon_endpoint_disables_statement_cache() -> None:
    args = _dbapi_args(
        "postgresql://u:p@ep-x-123-pooler.us-east-2.aws.neon.tech/db?sslmode=require"
    )
    assert args.get("statement_cache_size") == 0
    assert args.get("ssl") is True


def test_direct_neon_endpoint_keeps_statement_cache() -> None:
    args = _dbapi_args("postgresql://u:p@ep-x-123.us-east-2.aws.neon.tech/db?sslmode=require")
    assert "statement_cache_size" not in args


def test_pgbouncer_param_disables_statement_cache() -> None:
    args = _dbapi_args("postgresql://u:p@ep-x.us-east-2.aws.neon.tech/db?pgbouncer=true")
    assert args.get("statement_cache_size") == 0


def test_pgbouncer_is_stripped_from_url() -> None:
    clean, dropped = strip_asyncpg_unsupported(
        "postgresql+asyncpg://u:p@h/db?pgbouncer=true&sslmode=require"
    )
    assert "pgbouncer" not in clean
    assert dropped["pgbouncer"] == "true"

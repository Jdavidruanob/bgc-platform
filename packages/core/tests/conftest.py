"""
SQLite in-memory adapter for testing coop-core.

The adapter translates %s placeholders (psycopg3 style) to ? (sqlite3 style)
and wraps rows so they are accessible both by index and by column name.
"""
import sqlite3
from typing import Any, Generator

import pytest

from coop_core.db.schema import CONFIG_DEFAULTS, SCHEMA_SQL
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.repositories.recibos_repo import RecibosRepository
from coop_core.repositories.socios_repo import SociosRepository


def _adapt(sql: str) -> str:
    return sql.replace("%s", "?")


class _SqliteCursor:
    def __init__(self, raw: sqlite3.Cursor) -> None:
        self._raw = raw

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "_SqliteCursor":
        self._raw.execute(_adapt(sql), params)
        return self

    def executemany(self, sql: str, params_list: Any) -> None:
        self._raw.executemany(_adapt(sql), params_list)

    def fetchone(self) -> Any:
        return self._raw.fetchone()

    def fetchall(self) -> list[Any]:
        return self._raw.fetchall()

    @property
    def description(self) -> Any:
        return self._raw.description

    @property
    def lastrowid(self) -> int | None:
        return self._raw.lastrowid


class SqliteTestConn:
    """Wraps sqlite3 connection to match DbConnection Protocol with %s paramstyle."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        raw.row_factory = sqlite3.Row
        self._raw = raw

    def cursor(self) -> _SqliteCursor:
        return _SqliteCursor(self._raw.cursor())

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()


def _make_conn() -> SqliteTestConn:
    raw = sqlite3.connect(":memory:")
    raw.execute("PRAGMA foreign_keys = ON")
    conn = SqliteTestConn(raw)
    # Execute each statement separately (sqlite3 doesn't support multiple statements)
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            raw.execute(stmt)
    raw.commit()
    # Initialize config defaults
    for key, val in CONFIG_DEFAULTS.items():
        raw.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, val)
        )
    raw.commit()
    return conn


@pytest.fixture()
def conn() -> Generator[SqliteTestConn, None, None]:
    yield _make_conn()


@pytest.fixture()
def repos(conn: SqliteTestConn) -> dict[str, Any]:
    return {
        "conn": conn,
        "socios": SociosRepository(conn),
        "creditos": CreditosRepository(conn),
        "liquidaciones": LiquidacionesRepository(conn),
        "recibos": RecibosRepository(conn),
        "config": ConfigRepository(conn),
        "auxiliar": AuxiliarRepository(conn),
    }

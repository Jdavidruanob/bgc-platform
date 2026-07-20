"""Adapta SQLite en memoria como DbConnection para tests de coop-api."""

import os
import sqlite3
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from coop_core.db.schema import CONFIG_DEFAULTS, SCHEMA_SQL

os.environ.setdefault("API_SECRET_TOKEN", "test-secret")


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


class SqliteTestConn:
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
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    raw.execute("PRAGMA foreign_keys = ON")
    conn = SqliteTestConn(raw)
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            raw.execute(stmt)
    raw.commit()
    for key, val in CONFIG_DEFAULTS.items():
        raw.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, val))
    raw.commit()
    return conn


@pytest.fixture()
def db_conn() -> Generator[SqliteTestConn, None, None]:
    yield _make_conn()


@pytest.fixture()
def client(db_conn: SqliteTestConn) -> Generator[TestClient, None, None]:
    from coop_api.deps import get_db
    from coop_api.main import app

    app.dependency_overrides[get_db] = lambda: db_conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

"""El arranque no debe colgarse ni caerse si otra conexión bloquea una tabla."""

from typing import Any

import psycopg
import pytest
from coop_api.arranque import LOCK_TIMEOUT, aplicar_esquema


class _ConexionFalsa:
    def __init__(self, bloquea: tuple[str, ...] = (), falla: tuple[str, ...] = ()) -> None:
        self.ejecutadas: list[str] = []
        self._bloquea = bloquea
        self._falla = falla

    def execute(self, sql: str, params: Any = None) -> None:
        self.ejecutadas.append(sql)
        if any(t in sql for t in self._bloquea):
            raise psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")
        if any(t in sql for t in self._falla):
            raise psycopg.errors.SyntaxError("error real")


def test_pone_el_lock_timeout_antes_que_nada() -> None:
    conn = _ConexionFalsa()
    aplicar_esquema(conn, "CREATE TABLE x ()", ("ALTER TABLE a ADD COLUMN IF NOT EXISTS b INT",), {"k": "v"})
    assert conn.ejecutadas[0] == f"SET lock_timeout = '{LOCK_TIMEOUT}'"


def test_aplica_todo_si_no_hay_bloqueos() -> None:
    conn = _ConexionFalsa()
    omitidas = aplicar_esquema(
        conn, "CREATE TABLE x ()", ("ALTER TABLE a ADD COLUMN IF NOT EXISTS b INT",), {"k": "v"}
    )
    assert omitidas == []
    assert len(conn.ejecutadas) == 4  # SET + esquema + 1 migración + 1 config


def test_un_bloqueo_omite_esa_migracion_y_sigue_con_las_demas(caplog: pytest.LogCaptureFixture) -> None:
    conn = _ConexionFalsa(bloquea=("TABLE socios",))
    migraciones = (
        "ALTER TABLE socios ADD COLUMN IF NOT EXISTS foto BYTEA",
        "ALTER TABLE otra ADD COLUMN IF NOT EXISTS z INT",
    )
    with caplog.at_level("WARNING", logger="coop_api.arranque"):
        omitidas = aplicar_esquema(conn, "CREATE TABLE x ()", migraciones, {"k": "v"})
    assert omitidas == [migraciones[0]]
    assert migraciones[1] in conn.ejecutadas  # la siguiente sí se aplicó
    assert any("se omite" in r.getMessage() for r in caplog.records)


def test_un_error_que_no_es_de_bloqueo_si_se_propaga() -> None:
    conn = _ConexionFalsa(falla=("ALTER TABLE a",))
    with pytest.raises(psycopg.errors.SyntaxError):
        aplicar_esquema(conn, "CREATE TABLE x ()", ("ALTER TABLE a ADD COLUMN b",), {})

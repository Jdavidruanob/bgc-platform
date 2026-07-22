#!/usr/bin/env python3
"""Carga inicial de datos desde la SQLite histórica (BGC-software.db) a Postgres.

Diferencia con migrate_sqlite_to_postgres.py:
  - La DB antigua NO tiene historial (recibos/auxiliar vacíos) ni config.
  - saldo_en_caja se computa como SUM(socios.saldo) — no se lee de config.
  - Solo migra los datos maestros: socios, creditos, socio_credito, liquidaciones.

Uso:
    uv run python scripts/seed_from_sqlite.py \\
        --sqlite /ruta/BGC-software.db \\
        --postgres "postgres://user:pass@host/dbname?sslmode=require"
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed inicial BGC-software.db → Postgres")
    parser.add_argument("--sqlite", required=True, help="Ruta al archivo .db de SQLite")
    parser.add_argument("--postgres", required=True, help="Connection string de Postgres")
    args = parser.parse_args()

    print(f"[seed] Origen:  {args.sqlite}")
    print(f"[seed] Destino: {args.postgres[:40]}...")

    try:
        import psycopg
    except ImportError:
        sys.exit("Error: psycopg no instalado. Corre: uv sync --all-packages")

    # ── Leer SQLite ───────────────────────────────────────────────────────────
    print("[seed] Leyendo SQLite...")
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row

    socios       = [dict(r) for r in sqlite_conn.execute("SELECT * FROM socios")]
    creditos     = [dict(r) for r in sqlite_conn.execute("SELECT * FROM creditos")]
    socio_cred   = [dict(r) for r in sqlite_conn.execute("SELECT * FROM socio_credito")]
    liquidaciones = [dict(r) for r in sqlite_conn.execute("SELECT * FROM liquidaciones")]
    sqlite_conn.close()

    suma_saldos = sum(int(s["saldo"] or 0) for s in socios)
    n_pagadas   = sum(1 for liq in liquidaciones if liq.get("fecha_pago"))

    print(f"[seed]   socios:       {len(socios)}")
    print(f"[seed]   creditos:     {len(creditos)}")
    print(f"[seed]   socio_credito:{len(socio_cred)}")
    print(f"[seed]   liquidaciones:{len(liquidaciones)}")
    print(f"[seed]   suma saldos:  ${suma_saldos:,}")
    print(f"[seed]   cuotas pagas: {n_pagadas}")

    # ── Migrar ────────────────────────────────────────────────────────────────
    with psycopg.connect(args.postgres) as pg:
        _verificar_destino_vacio(pg)

        print("[seed] Creando schema...")
        _crear_schema(pg)

        print("[seed] Insertando datos maestros...")
        _insertar_socios(pg, socios)
        _insertar_creditos(pg, creditos)
        with pg.cursor() as cur:
            cur.executemany(
                "INSERT INTO socio_credito (socio_id, credito_letra) VALUES (%s, %s)",
                [(r["socio_id"], r["credito_letra"]) for r in socio_cred],
            )
        _insertar_liquidaciones(pg, liquidaciones)

        print(f"[seed] Actualizando saldo_en_caja = {suma_saldos:,}...")
        pg.execute(
            "INSERT INTO config (key, value) VALUES ('saldo_en_caja', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (str(suma_saldos),),
        )

        _resetear_secuencias(pg)

        print("[seed] Verificando integridad...")
        errores = _verificar(pg, socios, creditos, liquidaciones, suma_saldos, n_pagadas)
        if errores:
            pg.rollback()
            print("\n[FALLO] Rollback — verificaciones fallidas:")
            for e in errores:
                print(f"  ✗ {e}")
            sys.exit(1)

        pg.commit()

    print("\n[OK] Seed completado.")
    print(f"     socios:       {len(socios)}")
    print(f"     creditos:     {len(creditos)}")
    print(f"     liquidaciones:{len(liquidaciones)}")
    print(f"     saldo_en_caja:{suma_saldos:,}")


def _verificar_destino_vacio(pg: Any) -> None:
    try:
        n = pg.execute("SELECT COUNT(*) FROM socios").fetchone()[0]
        if n > 0:
            sys.exit(f"[ABORT] Postgres ya tiene {n} socios. Este script solo corre en DB vacía.")
    except Exception:
        pg.rollback()  # tabla no existe aún — resetear transacción abortada


def _crear_schema(pg: Any) -> None:
    from coop_api.postgres_schema import CONFIG_DEFAULTS, SCHEMA_POSTGRES
    pg.execute(SCHEMA_POSTGRES)
    for key, value in CONFIG_DEFAULTS.items():
        pg.execute(
            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            (key, value),
        )


def _insertar_socios(pg: Any, socios: list[dict[str, Any]]) -> None:
    columnas = ["id", "cc", "nombres", "apellidos", "saldo", "celular",
                "photo_path", "whatsapp_e164", "optin_whatsapp_fecha", "created_at"]
    sql = (f"INSERT INTO socios ({', '.join(columnas)}) OVERRIDING SYSTEM VALUE "
           f"VALUES ({', '.join(['%s'] * len(columnas))})")
    with pg.cursor() as cur:
        cur.executemany(sql, [tuple(s.get(c) for c in columnas) for s in socios])


def _insertar_creditos(pg: Any, creditos: list[dict[str, Any]]) -> None:
    columnas = ["letra", "capital", "interes", "no_cuotas", "fecha_inicio"]
    sql = (f"INSERT INTO creditos ({', '.join(columnas)}) OVERRIDING SYSTEM VALUE "
           f"VALUES ({', '.join(['%s'] * len(columnas))})")
    with pg.cursor() as cur:
        cur.executemany(sql, [tuple(c.get(col) for col in columnas) for c in creditos])


def _insertar_liquidaciones(pg: Any, liquidaciones: list[dict[str, Any]]) -> None:
    columnas = ["id", "credito_letra", "nro_cuota", "fecha_vencimiento",
                "valor_cuota", "interes_mes", "cuota_mensual", "saldo_capital",
                "fecha_pago", "interes_mora", "mora_aplicada",
                "notif_prev_enviada", "notif_venc_enviada"]
    sql = (f"INSERT INTO liquidaciones ({', '.join(columnas)}) OVERRIDING SYSTEM VALUE "
           f"VALUES ({', '.join(['%s'] * len(columnas))})")
    with pg.cursor() as cur:
        cur.executemany(sql, [tuple(liq.get(c) for c in columnas) for liq in liquidaciones])


def _resetear_secuencias(pg: Any) -> None:
    for tabla, col in [("socios", "id"), ("creditos", "letra"), ("liquidaciones", "id")]:
        pg.execute(
            f"SELECT setval(pg_get_serial_sequence('{tabla}', '{col}'), "
            f"COALESCE((SELECT MAX({col}) FROM {tabla}), 0) + 1, false)"
        )


def _verificar(
    pg: Any,
    socios: list[dict[str, Any]],
    creditos: list[dict[str, Any]],
    liquidaciones: list[dict[str, Any]],
    suma_saldos_esperada: int,
    n_pagadas_esperadas: int,
) -> list[str]:
    errores: list[str] = []

    # Conteos
    for tabla, esperado in [("socios", len(socios)), ("creditos", len(creditos)),
                             ("liquidaciones", len(liquidaciones))]:
        real = pg.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        if real != esperado:
            errores.append(f"{tabla}: esperado={esperado}, en Postgres={real}")

    # Suma de saldos == saldo_en_caja
    suma_pg = pg.execute("SELECT SUM(saldo) FROM socios").fetchone()[0] or 0
    caja_pg = int(pg.execute("SELECT value FROM config WHERE key='saldo_en_caja'").fetchone()[0])
    if suma_pg != caja_pg:
        errores.append(f"SUM(saldo)={suma_pg} ≠ saldo_en_caja={caja_pg}")

    # Cuotas pagadas
    n_pg = pg.execute("SELECT COUNT(*) FROM liquidaciones WHERE fecha_pago IS NOT NULL").fetchone()[0]
    if n_pg != n_pagadas_esperadas:
        errores.append(f"cuotas pagadas: esperado={n_pagadas_esperadas}, Postgres={n_pg}")

    if not errores:
        print("[seed] ✓ Todas las verificaciones OK")
    return errores


if __name__ == "__main__":
    main()

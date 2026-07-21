#!/usr/bin/env python3
"""Migración única de datos desde SQLite (BGC-software.db) hacia Postgres de staging/producción.

Uso:
    uv run python scripts/migrate_sqlite_to_postgres.py \\
        --sqlite path/a/BGC-software.db \\
        --postgres "postgres://user:pass@host/dbname?sslmode=require"

El script:
  1. Crea el schema en Postgres (idempotente — CREATE TABLE IF NOT EXISTS).
  2. Inserta todos los datos preservando los IDs originales (OVERRIDING SYSTEM VALUE).
  3. Resetea las secuencias de auto-incremento al máximo ID migrado.
  4. Ejecuta verificaciones de integridad y aborta con rollback si alguna falla.

Está diseñado para correr UNA SOLA VEZ contra una base de datos Postgres vacía.
Si ya hay datos en Postgres abortará antes de insertar.

PUNTO DE NO RETORNO: ejecutar con --postgres que apunte a producción
reemplaza la SQLite como fuente de verdad. Hacer backup antes.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrar BGC-software.db → Postgres")
    parser.add_argument("--sqlite", required=True, help="Ruta al archivo .db de SQLite")
    parser.add_argument("--postgres", required=True, help="Connection string de Postgres")
    args = parser.parse_args()

    print(f"[migración] Origen:  {args.sqlite}")
    print(f"[migración] Destino: {args.postgres[:30]}...")

    try:
        import psycopg
    except ImportError:
        sys.exit("Error: psycopg no está instalado. Corre: uv sync --all-packages")

    # ── Leer datos de SQLite ────────────────────────────────────────────────
    print("[migración] Leyendo SQLite...")
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row
    datos = _leer_sqlite(sqlite_conn)
    sqlite_conn.close()

    totales = {tabla: len(filas) for tabla, filas in datos.items()}
    for tabla, n in totales.items():
        print(f"           {tabla}: {n} filas")

    # ── Migrar a Postgres ───────────────────────────────────────────────────
    with psycopg.connect(args.postgres) as pg:
        _verificar_destino_vacio(pg)
        print("[migración] Destino vacío. Iniciando transacción...")
        _crear_schema(pg)
        _insertar_datos(pg, datos)
        _resetear_secuencias(pg)
        print("[migración] Corriendo verificaciones...")
        errores = _verificar_integridad(pg, datos)
        if errores:
            pg.rollback()
            print("\n[FALLO] Verificaciones fallidas — se hizo rollback:")
            for e in errores:
                print(f"  ✗ {e}")
            sys.exit(1)
        pg.commit()

    print("\n[OK] Migración completada.")
    print(f"     socios:     {totales.get('socios', 0)}")
    print(f"     creditos:   {totales.get('creditos', 0)}")
    print(f"     recibos:    {totales.get('recibos', 0)}")
    print(f"     auxiliar:   {totales.get('auxiliar', 0)}")


# ── Lectura de SQLite ──────────────────────────────────────────────────────────

def _leer_sqlite(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    tablas = [
        "config",
        "socios",
        "creditos",
        "socio_credito",
        "liquidaciones",
        "recibos",
        "detalle_recibo",
        "auxiliar",
        "notificaciones_whatsapp",
        "idempotency_keys",
        "audit_log",
    ]
    datos: dict[str, list[dict[str, Any]]] = {}
    cursor = conn.cursor()
    for tabla in tablas:
        try:
            cursor.execute(f"SELECT * FROM {tabla}")  # noqa: S608
            filas = cursor.fetchall()
            datos[tabla] = [dict(f) for f in filas]
        except sqlite3.OperationalError:
            datos[tabla] = []
    return datos


# ── Schema en Postgres ─────────────────────────────────────────────────────────

def _crear_schema(pg: Any) -> None:
    from coop_api.postgres_schema import CONFIG_DEFAULTS, SCHEMA_POSTGRES

    pg.execute(SCHEMA_POSTGRES)
    for key, value in CONFIG_DEFAULTS.items():
        pg.execute(
            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            (key, value),
        )
    print("[migración] Schema creado.")


def _verificar_destino_vacio(pg: Any) -> None:
    try:
        cursor = pg.execute("SELECT COUNT(*) FROM socios")
        n = cursor.fetchone()[0]
        if n > 0:
            sys.exit(
                f"[ABORT] La tabla socios ya tiene {n} filas en Postgres. "
                "Este script solo corre contra una base de datos vacía."
            )
    except Exception:
        pass  # tabla no existe aún — OK


# ── Inserts con IDs preservados ────────────────────────────────────────────────

def _insertar_datos(pg: Any, datos: dict[str, list[dict[str, Any]]]) -> None:
    # Orden respeta FK constraints
    _insertar_config(pg, datos.get("config", []))
    _insertar_tabla(pg, "socios", datos.get("socios", []),
                    with_identity=True,
                    columnas=["id", "cc", "nombres", "apellidos", "saldo",
                               "celular", "photo_path", "whatsapp_e164",
                               "optin_whatsapp_fecha", "created_at"])
    _insertar_tabla(pg, "creditos", datos.get("creditos", []),
                    with_identity=True,
                    columnas=["letra", "capital", "interes", "no_cuotas", "fecha_inicio"])
    _insertar_tabla(pg, "socio_credito", datos.get("socio_credito", []),
                    columnas=["socio_id", "credito_letra"])
    _insertar_tabla(pg, "liquidaciones", datos.get("liquidaciones", []),
                    with_identity=True,
                    columnas=["id", "credito_letra", "nro_cuota", "fecha_vencimiento",
                               "valor_cuota", "interes_mes", "cuota_mensual", "saldo_capital",
                               "fecha_pago", "interes_mora", "mora_aplicada",
                               "notif_prev_enviada", "notif_venc_enviada"])
    _insertar_tabla(pg, "recibos", datos.get("recibos", []),
                    with_identity=True,
                    columnas=["id", "socio_id", "fecha"])
    _insertar_tabla(pg, "detalle_recibo", datos.get("detalle_recibo", []),
                    with_identity=True,
                    columnas=["id", "recibo_id", "tipo_operacion", "socio_id",
                               "credito_letra", "nro_cuota", "monto", "abono_mora"])
    _insertar_tabla(pg, "auxiliar", datos.get("auxiliar", []),
                    with_identity=True,
                    columnas=["id", "fecha", "tipo", "socio", "recibo",
                               "monto", "saldo", "cuota", "id_credito"])
    _insertar_tabla(pg, "notificaciones_whatsapp", datos.get("notificaciones_whatsapp", []),
                    with_identity=True,
                    columnas=["id", "socio_id", "numero_e164", "texto", "estado",
                               "intentos", "created_at", "ultimo_intento_at", "error"])
    _insertar_tabla(pg, "idempotency_keys", datos.get("idempotency_keys", []),
                    columnas=["key", "endpoint", "payload_hash", "response_json", "created_at"])
    _insertar_tabla(pg, "audit_log", datos.get("audit_log", []),
                    with_identity=True,
                    columnas=["id", "telegram_message_id", "chat_id", "audio_url",
                               "transcripcion", "intencion_json", "operacion_tipo",
                               "operacion_id", "created_at"])
    print("[migración] Datos insertados.")


def _insertar_config(pg: Any, filas: list[dict[str, Any]]) -> None:
    for f in filas:
        pg.execute(
            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (f["key"], f["value"]),
        )


def _insertar_tabla(
    pg: Any,
    tabla: str,
    filas: list[dict[str, Any]],
    columnas: list[str],
    with_identity: bool = False,
) -> None:
    if not filas:
        return
    cols_str = ", ".join(columnas)
    placeholders = ", ".join(["%s"] * len(columnas))
    identity_clause = "OVERRIDING SYSTEM VALUE" if with_identity else ""
    sql = f"INSERT INTO {tabla} ({cols_str}) {identity_clause} VALUES ({placeholders})"  # noqa: S608
    filas_valores = [
        tuple(f.get(col) for col in columnas)
        for f in filas
    ]
    pg.executemany(sql, filas_valores)


# ── Resetear secuencias ────────────────────────────────────────────────────────

_TABLAS_CON_IDENTITY = [
    ("socios", "id"),
    ("creditos", "letra"),
    ("liquidaciones", "id"),
    ("recibos", "id"),
    ("detalle_recibo", "id"),
    ("auxiliar", "id"),
    ("notificaciones_whatsapp", "id"),
    ("audit_log", "id"),
]


def _resetear_secuencias(pg: Any) -> None:
    for tabla, col in _TABLAS_CON_IDENTITY:
        pg.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{tabla}', '{col}'),
                COALESCE((SELECT MAX({col}) FROM {tabla}), 0) + 1,
                false
            )
            """  # noqa: S608
        )
    print("[migración] Secuencias reseteadas.")


# ── Verificaciones post-migración ──────────────────────────────────────────────

def _verificar_integridad(
    pg: Any,
    datos: dict[str, list[dict[str, Any]]],
) -> list[str]:
    errores: list[str] = []

    # 1. Suma de saldos de socios == saldo_en_caja en config
    cur = pg.execute("SELECT SUM(saldo) FROM socios")
    suma_saldos = cur.fetchone()[0] or 0
    cur2 = pg.execute("SELECT value FROM config WHERE key = 'saldo_en_caja'")
    row = cur2.fetchone()
    saldo_caja_config = int(row[0]) if row else 0
    if suma_saldos != saldo_caja_config:
        errores.append(
            f"Suma de saldos ({suma_saldos}) ≠ saldo_en_caja en config ({saldo_caja_config})"
        )

    # 2. Número de cuotas pagadas == filas con fecha_pago NOT NULL en liquidaciones
    n_pagadas_sqlite = sum(
        1 for f in datos.get("liquidaciones", []) if f.get("fecha_pago") is not None
    )
    cur3 = pg.execute("SELECT COUNT(*) FROM liquidaciones WHERE fecha_pago IS NOT NULL")
    n_pagadas_pg = cur3.fetchone()[0]
    if n_pagadas_sqlite != n_pagadas_pg:
        errores.append(
            f"Cuotas pagadas: SQLite={n_pagadas_sqlite} ≠ Postgres={n_pagadas_pg}"
        )

    # 3. Número de socios, créditos y recibos coincide
    for tabla in ("socios", "creditos", "recibos", "auxiliar"):
        n_sqlite = len(datos.get(tabla, []))
        cur_t = pg.execute(f"SELECT COUNT(*) FROM {tabla}")  # noqa: S608
        n_pg = cur_t.fetchone()[0]
        if n_sqlite != n_pg:
            errores.append(f"Tabla {tabla}: SQLite={n_sqlite} ≠ Postgres={n_pg}")

    # 4. Últimos 10 registros del auxiliar coinciden (fecha + monto)
    aux_sqlite = sorted(
        datos.get("auxiliar", []),
        key=lambda f: (f.get("id") or 0),
        reverse=True,
    )[:10]
    cur4 = pg.execute(
        "SELECT id, fecha, monto FROM auxiliar ORDER BY id DESC LIMIT 10"
    )
    aux_pg = [{"id": r[0], "fecha": str(r[1]), "monto": r[2]} for r in cur4.fetchall()]

    if len(aux_sqlite) != len(aux_pg):
        errores.append(
            f"Últimos registros de auxiliar: SQLite={len(aux_sqlite)} ≠ Postgres={len(aux_pg)}"
        )
    else:
        for s, p in zip(aux_sqlite, aux_pg):
            if int(s.get("monto", 0)) != int(p["monto"]):
                errores.append(
                    f"Auxiliar id={s.get('id')}: monto SQLite={s.get('monto')} ≠ Postgres={p['monto']}"
                )
                break

    if not errores:
        print("[migración] ✓ Verificaciones OK")

    return errores


if __name__ == "__main__":
    main()

"""Esquema y migraciones que corre la API al arrancar.

Cada migración (`ALTER TABLE ... IF NOT EXISTS`) pide un bloqueo exclusivo de
la tabla aunque la columna ya exista. Si otro cliente deja una transacción
abierta sobre esa tabla (pasó el 2026-10-11 con la app de escritorio, 54 min
`idle in transaction`), el `ALTER` espera sin límite y la API nunca termina de
arrancar: producción cae con 502. Por eso aquí cada sentencia tiene un tiempo
máximo de espera por el bloqueo, y si no lo consigue se OMITE con un aviso en
vez de colgar el servicio. Las migraciones son idempotentes: la próxima vez
que la API arranque (o se redespliegue) se vuelve a intentar.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = "5s"


def aplicar_esquema(
    conn: Any,
    esquema: str,
    migraciones: Iterable[str],
    config_defaults: dict[str, str],
) -> list[str]:
    """Aplica esquema, migraciones y valores por defecto sobre una conexión en
    autocommit (cada sentencia es su propia transacción, así lo que sí se pudo
    aplicar queda aplicado aunque otra se omita). Devuelve las sentencias que
    se omitieron por bloqueo."""
    conn.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
    omitidas: list[str] = []

    sentencias: list[tuple[str, tuple[Any, ...] | None]] = [(esquema, None)]
    sentencias += [(m, None) for m in migraciones]
    sentencias += [
        ("INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (k, v))
        for k, v in config_defaults.items()
    ]

    for sql, params in sentencias:
        try:
            if params is None:
                conn.execute(sql)
            else:
                conn.execute(sql, params)
        except psycopg.errors.LockNotAvailable:
            omitidas.append(sql)
            logger.warning(
                "Arranque: no se pudo obtener el bloqueo en %s s, se omite (otra conexión tiene una "
                "transacción abierta; se reintenta en el próximo arranque): %s",
                LOCK_TIMEOUT.rstrip("s"),
                " ".join(sql.split())[:120],
            )
    return omitidas

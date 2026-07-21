"""Manejo de idempotencia para endpoints POST."""

from __future__ import annotations

import hashlib
import json

from coop_core.db.connection import DbConnection


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def check(conn: DbConnection, key: str, endpoint: str, payload_json: str) -> dict[str, object] | None:
    """
    Retorna el response guardado si la key ya existe con el mismo payload.
    Lanza ValueError si la key existe con payload diferente (409).
    Retorna None si es la primera vez que se usa esta key.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT payload_hash, response_json FROM idempotency_keys WHERE key = %s",
        (key,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    stored_hash, response_json = str(row[0]), str(row[1])
    if stored_hash != _hash(payload_json):
        raise ValueError("IDEMPOTENCY_CONFLICT")
    result: dict[str, object] = json.loads(response_json)
    return result


def store(
    conn: DbConnection, key: str, endpoint: str, payload_json: str, response: dict[str, object]
) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO idempotency_keys (key, endpoint, payload_hash, response_json)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO NOTHING
        """,
        (key, endpoint, _hash(payload_json), json.dumps(response)),
    )

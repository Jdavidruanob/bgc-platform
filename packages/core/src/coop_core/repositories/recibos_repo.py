from typing import Any

from coop_core.db.connection import DbConnection


class RecibosRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def create(self, socio_id: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO recibos (socio_id) VALUES (%s) RETURNING id",
            (socio_id,),
        )
        row = cursor.fetchone()
        return int(row[0])

    def find_by_id(self, recibo_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT id, socio_id, fecha FROM recibos WHERE id = %s", (recibo_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

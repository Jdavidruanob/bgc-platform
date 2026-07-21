from typing import Any

from coop_core.db.connection import DbConnection


class NotificacionesRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def create(self, socio_id: int, numero_e164: str, texto: str) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO notificaciones_whatsapp (socio_id, numero_e164, texto)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (socio_id, numero_e164, texto),
        )
        return int(cursor.fetchone()[0])

    def find_pending(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, socio_id, numero_e164, texto, created_at
            FROM notificaciones_whatsapp
            WHERE estado = 'pendiente'
            ORDER BY created_at ASC
            """,
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def update_estado(self, notif_id: int, estado: str, error: str | None = None) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE notificaciones_whatsapp
            SET estado = %s, error = %s, intentos = intentos + 1,
                ultimo_intento_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (estado, error, notif_id),
        )

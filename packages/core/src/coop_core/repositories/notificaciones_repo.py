from typing import Any

from coop_core.db.connection import DbConnection


class NotificacionesRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def create(
        self,
        socio_id: int,
        numero_e164: str,
        texto: str,
        documento_tipo: str | None = None,
        documento_id: int | None = None,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO notificaciones_whatsapp
                (socio_id, numero_e164, texto, documento_tipo, documento_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (socio_id, numero_e164, texto, documento_tipo, documento_id),
        )
        return int(cursor.fetchone()[0])

    def find_pending(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT n.id, n.socio_id, n.numero_e164, n.texto, n.created_at,
                   n.documento_tipo, n.documento_id,
                   s.nombres, s.apellidos
            FROM notificaciones_whatsapp n
            JOIN socios s ON s.id = n.socio_id
            WHERE n.estado = 'pendiente'
            ORDER BY n.created_at ASC
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

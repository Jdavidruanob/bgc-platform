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
        detalle: str | None = None,
        estado: str = "pendiente",
    ) -> int:
        """`estado='borrador'` deja la notificación redactada pero SIN enviar,
        esperando que el administrador la apruebe (ver `aprobar_por_documento`).
        El procesador de la cola solo recoge las que quedan en 'pendiente'."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO notificaciones_whatsapp
                (socio_id, numero_e164, texto, documento_tipo, documento_id, detalle, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (socio_id, numero_e164, texto, documento_tipo, documento_id, detalle, estado),
        )
        return int(cursor.fetchone()[0])

    def find_borradores_por_documento(self, documento_tipo: str, documento_id: int) -> list[dict[str, Any]]:
        """Borradores (aún sin aprobar) de un documento, con el nombre del socio."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT n.id, n.socio_id, s.nombres, s.apellidos
            FROM notificaciones_whatsapp n
            JOIN socios s ON s.id = n.socio_id
            WHERE n.estado = 'borrador'
              AND n.documento_tipo = %s AND n.documento_id = %s
            ORDER BY n.id ASC
            """,
            (documento_tipo, documento_id),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def aprobar_por_documento(self, documento_tipo: str, documento_id: int) -> None:
        """Pasa los borradores de ese documento a 'pendiente' (para que el
        procesador los envíe)."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE notificaciones_whatsapp SET estado = 'pendiente'
            WHERE estado = 'borrador' AND documento_tipo = %s AND documento_id = %s
            """,
            (documento_tipo, documento_id),
        )

    def descartar_por_documento(self, documento_tipo: str, documento_id: int) -> None:
        """Marca los borradores de ese documento como 'descartada' (el admin
        decidió no enviarlos)."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE notificaciones_whatsapp SET estado = 'descartada'
            WHERE estado = 'borrador' AND documento_tipo = %s AND documento_id = %s
            """,
            (documento_tipo, documento_id),
        )

    def find_pending(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT n.id, n.socio_id, n.numero_e164, n.texto, n.created_at,
                   n.documento_tipo, n.documento_id, n.detalle,
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

from datetime import datetime, timedelta
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

    def update_estado(
        self, notif_id: int, estado: str, error: str | None = None, wamid: str | None = None
    ) -> None:
        """`wamid` es el id que devuelve Meta al aceptar el envío; sin él no se
        puede cruzar después con el estado de entrega (ver `registrar_entrega`)."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE notificaciones_whatsapp
            SET estado = %s, error = %s, intentos = intentos + 1,
                ultimo_intento_at = CURRENT_TIMESTAMP,
                wamid = COALESCE(%s, wamid)
            WHERE id = %s
            """,
            (estado, error, wamid, notif_id),
        )

    def registrar_entrega(self, wamid: str, estado: str, error: str | None = None) -> bool:
        """Guarda lo que Meta informó de un mensaje (`sent`, `delivered`, `read`
        o `failed`). Devuelve False si ninguna notificación tiene ese wamid.

        Meta puede mandar los estados en desorden y reintentar webhooks, así
        que la regla es: `failed` siempre gana, `delivered`/`read` no se
        degradan a `sent`, y repetir el mismo estado no hace nada. `read`
        implica entregado y se guarda como `delivered`."""
        if estado not in ("sent", "delivered", "read", "failed"):
            return True  # estados que no usamos (p. ej. 'deleted'): se ignoran
        nuevo = "delivered" if estado == "read" else estado
        cursor = self._conn.cursor()
        cursor.execute("SELECT entrega_estado FROM notificaciones_whatsapp WHERE wamid = %s", (wamid,))
        filas = cursor.fetchall()
        if not filas:
            return False
        actual = filas[0][0]
        if actual == "failed" and nuevo != "failed":
            return True
        if actual == "delivered" and nuevo == "sent":
            return True
        if nuevo == "failed":
            cursor.execute(
                """
                UPDATE notificaciones_whatsapp
                SET entrega_estado = 'failed', entrega_error = %s
                WHERE wamid = %s AND (entrega_estado IS NULL OR entrega_estado <> 'failed')
                """,
                (error, wamid),
            )
        else:
            cursor.execute(
                "UPDATE notificaciones_whatsapp SET entrega_estado = %s WHERE wamid = %s",
                (nuevo, wamid),
            )
        return True

    def find_entregas_por_avisar(self, minutos_sin_confirmacion: int) -> list[dict[str, Any]]:
        """Notificaciones cuyo resultado real en WhatsApp todavía no se le
        informó al operador: las que Meta confirmó como `delivered` o `failed`,
        y las aceptadas por Meta que llevan `minutos_sin_confirmacion` sin
        ningún estado (`resultado = 'sin_confirmacion'`)."""
        cursor = self._conn.cursor()
        # El corte se calcula con el reloj de la propia base (no el de Python)
        # para que sea coherente con `ultimo_intento_at`, que escribe la base.
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        ahora = cursor.fetchone()[0]
        if isinstance(ahora, str):
            ahora = datetime.fromisoformat(ahora)
        corte = (ahora - timedelta(minutes=minutos_sin_confirmacion)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            SELECT n.id, n.documento_tipo, n.detalle, n.entrega_error, s.nombres, s.apellidos,
                   CASE WHEN n.entrega_estado IN ('delivered', 'failed')
                        THEN n.entrega_estado ELSE 'sin_confirmacion' END AS resultado
            FROM notificaciones_whatsapp n
            JOIN socios s ON s.id = n.socio_id
            WHERE n.wamid IS NOT NULL
              AND n.entrega_aviso_at IS NULL
              AND (
                    n.entrega_estado IN ('delivered', 'failed')
                    OR (n.ultimo_intento_at IS NOT NULL
                        AND n.ultimo_intento_at <= %s)
                  )
            ORDER BY n.id ASC
            """,
            (corte,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def marcar_entregas_avisadas(self, ids: list[int]) -> None:
        cursor = self._conn.cursor()
        for notif_id in ids:
            cursor.execute(
                "UPDATE notificaciones_whatsapp SET entrega_aviso_at = CURRENT_TIMESTAMP WHERE id = %s",
                (notif_id,),
            )

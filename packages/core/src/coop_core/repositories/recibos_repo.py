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

    def add_detalle_salario(self, recibo_id: int, socio_id: int, monto: int) -> None:
        """Línea de detalle de un pago de salario.

        No aporta información nueva —el monto ya queda en el auxiliar— pero es
        lo que permite eliminar el recibo después: el servicio de reversión se
        niega a tocar un recibo sin detalle ("El recibo no tiene operaciones
        registradas"), así que sin esta fila un salario pagado desde el bot
        quedaría imposible de deshacer.

        Va a nombre del tesorero, igual que el recibo, pero su saldo NO se toca:
        la plata es del administrador, no un aporte del socio.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO detalle_recibo (recibo_id, tipo_operacion, socio_id, monto)
            VALUES (%s, 'salario', %s, %s)
            """,
            (recibo_id, socio_id, monto),
        )

    def find_by_id(self, recibo_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT id, socio_id, fecha FROM recibos WHERE id = %s", (recibo_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row, strict=False))

    def sum_abono_mora(self) -> int:
        """Mora acumulada históricamente: suma de todos los abonos por mora
        registrados en los recibos. Igual que el BGC-software original."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(abono_mora), 0) FROM detalle_recibo")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

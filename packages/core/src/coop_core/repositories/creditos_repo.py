from typing import Any

from coop_core.db.connection import DbConnection


class CreditosRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def create(
        self,
        socio_ids: list[int],
        capital: int,
        interes: float,
        n_cuotas: int,
        fecha_inicio: str,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO creditos (capital, interes, no_cuotas, fecha_inicio)
            VALUES (%s, %s, %s, %s)
            RETURNING letra
            """,
            (capital, interes, n_cuotas, fecha_inicio),
        )
        row = cursor.fetchone()
        letra_id = int(row[0])
        for sid in socio_ids:
            cursor.execute(
                "INSERT INTO socio_credito (socio_id, credito_letra) VALUES (%s, %s)",
                (sid, letra_id),
            )
        return letra_id

    def save_amortization(self, cuotas: list[tuple[Any, ...]]) -> None:
        cursor = self._conn.cursor()
        cursor.executemany(
            """
            INSERT INTO liquidaciones
                (credito_letra, nro_cuota, fecha_vencimiento, valor_cuota,
                 interes_mes, cuota_mensual, saldo_capital)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            cuotas,
        )

    def find_by_letra(self, letra: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT c.letra, c.capital, c.interes, c.no_cuotas, c.fecha_inicio,
                   GROUP_CONCAT(s.nombres || ' ' || s.apellidos, ', ') AS socios_nombres
            FROM creditos c
            JOIN socio_credito sc ON sc.credito_letra = c.letra
            JOIN socios s ON s.id = sc.socio_id
            WHERE c.letra = %s
            GROUP BY c.letra
            """,
            (letra,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row, strict=False))

    def find_active_by_socio_id(self, socio_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT c.letra, c.capital, c.interes, c.no_cuotas
            FROM creditos c
            JOIN socio_credito sc ON c.letra = sc.credito_letra
            WHERE sc.socio_id = %s
            """,
            (socio_id,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def get_socio_ids(self, letra_id: int) -> list[int]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT socio_id FROM socio_credito WHERE credito_letra = %s",
            (letra_id,),
        )
        return [int(row[0]) for row in cursor.fetchall()]

    def update_no_cuotas(self, letra_id: int, new_total: int) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE creditos SET no_cuotas = %s WHERE letra = %s",
            (new_total, letra_id),
        )

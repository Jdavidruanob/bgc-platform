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
            SELECT letra, capital, interes, no_cuotas, fecha_inicio
            FROM creditos
            WHERE letra = %s
            """,
            (letra,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        credito = dict(zip(cols, row, strict=False))

        cursor.execute(
            """
            SELECT s.nombres, s.apellidos
            FROM socios s
            JOIN socio_credito sc ON sc.socio_id = s.id
            WHERE sc.credito_letra = %s
            """,
            (letra,),
        )
        nombres = [f"{r[0]} {r[1]}" for r in cursor.fetchall()]
        credito["socios_nombres"] = ", ".join(nombres)
        return credito

    def find_active_by_socio_id(self, socio_id: int) -> list[dict[str, Any]]:
        """Créditos ACTIVOS del socio: solo los que aún tienen alguna cuota sin
        cobrar. Un crédito ya saldado (todas las cuotas con fecha_pago) queda
        en la base pero no se devuelve, para que no estorbe al resolver un pago
        (evita el molesto "esa letra ya está pagada" al operar sobre los demás
        créditos del socio)."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT c.letra, c.capital, c.interes, c.no_cuotas
            FROM creditos c
            JOIN socio_credito sc ON c.letra = sc.credito_letra
            WHERE sc.socio_id = %s
              AND EXISTS (
                  SELECT 1 FROM liquidaciones l
                  WHERE l.credito_letra = c.letra AND l.fecha_pago IS NULL
              )
            """,
            (socio_id,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def next_letra(self) -> int:
        """Número de letra que tomaría el próximo crédito (informativo, para la
        confirmación). En esta cooperativa las letras son secuenciales sin
        borrados, así que MAX+1 coincide con el que asigna la base."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(letra), 0) + 1 FROM creditos")
        row = cursor.fetchone()
        return int(row[0]) if row else 1

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

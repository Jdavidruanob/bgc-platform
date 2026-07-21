from typing import Any

from coop_core.db.connection import DbConnection


class AuxiliarRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def add(
        self,
        fecha: str,
        tipo: str,
        socio: str,
        monto: int,
        saldo: int,
        recibo: int | None = None,
        cuota: int | None = None,
        id_credito: str | None = None,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO auxiliar (fecha, tipo, socio, recibo, monto, saldo, cuota, id_credito)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (fecha, tipo, socio, recibo, monto, saldo, cuota, id_credito),
        )

    def find_all(
        self,
        limit: int = 10,
        offset: int = 0,
        start_date: str | None = None,
        end_date: str | None = None,
        operation_type: str | None = None,
        socio_name: str | None = None,
        numero: int | None = None,
        letra_credito: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT id, fecha, tipo, socio, recibo, monto, saldo, cuota, id_credito FROM auxiliar WHERE 1=1"
        params: list[Any] = []

        if start_date:
            sql += " AND fecha >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND fecha <= %s"
            params.append(end_date)
        if operation_type:
            sql += " AND tipo = %s"
            params.append(operation_type)
        if socio_name:
            sql += " AND LOWER(socio) LIKE %s"
            params.append(f"%{socio_name.lower()}%")
        if numero is not None:
            sql += " AND recibo = %s"
            params.append(numero)
        if letra_credito:
            sql += " AND id_credito = %s"
            params.append(letra_credito)

        sql += " ORDER BY fecha DESC, id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        column_names = [d[0] for d in cursor.description]
        return [dict(zip(column_names, row, strict=False)) for row in rows]

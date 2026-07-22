"""Persistencia de los archivos de recibo (xlsx + pdf) en Postgres/SQLite."""

from __future__ import annotations

from typing import Literal

from coop_core.db.connection import DbConnection

TipoRecibo = Literal["aporte", "retiro", "pago", "combinado"]


class RecibosArchivosRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def guardar(
        self,
        recibo_id: int,
        tipo: TipoRecibo,
        xlsx_bytes: bytes,
        pdf_bytes: bytes,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO recibos_archivos (recibo_id, tipo, xlsx_bytes, pdf_bytes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (recibo_id) DO UPDATE SET
                tipo = EXCLUDED.tipo,
                xlsx_bytes = EXCLUDED.xlsx_bytes,
                pdf_bytes = EXCLUDED.pdf_bytes,
                created_at = CURRENT_TIMESTAMP
            """,
            (recibo_id, tipo, xlsx_bytes, pdf_bytes),
        )

    def obtener_pdf(self, recibo_id: int) -> bytes | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT pdf_bytes FROM recibos_archivos WHERE recibo_id = %s", (recibo_id,))
        row = cursor.fetchone()
        return bytes(row[0]) if row else None

    def obtener_xlsx(self, recibo_id: int) -> bytes | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT xlsx_bytes FROM recibos_archivos WHERE recibo_id = %s", (recibo_id,))
        row = cursor.fetchone()
        return bytes(row[0]) if row else None

    def listar(
        self, desde: str | None = None, hasta: str | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        cursor = self._conn.cursor()
        clauses: list[str] = []
        params: list[object] = []
        if desde:
            clauses.append("created_at >= %s")
            params.append(desde)
        if hasta:
            clauses.append("created_at <= %s")
            params.append(hasta)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        cursor.execute(
            f"""
            SELECT recibo_id, tipo, created_at
            FROM recibos_archivos
            {where}
            ORDER BY recibo_id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

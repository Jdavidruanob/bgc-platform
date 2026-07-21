from typing import Any

from coop_core.db.connection import DbConnection


class SociosRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def find_all(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT s.id, s.nombres, s.apellidos,
                   COALESCE(s.photo_path, '') AS photo_path,
                   COUNT(sc.credito_letra) AS creditos
            FROM socios s
            LEFT JOIN socio_credito sc ON s.id = sc.socio_id
            GROUP BY s.id
            ORDER BY s.nombres
        """)
        return [dict(zip([d[0] for d in cursor.description], row, strict=False)) for row in cursor.fetchall()]

    def find_all_full(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT s.*, COUNT(sc.credito_letra) AS creditos
            FROM socios s
            LEFT JOIN socio_credito sc ON s.id = sc.socio_id
            GROUP BY s.id
            ORDER BY s.nombres
        """)
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def find_by_id(self, member_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, cc, nombres, apellidos, celular, saldo, photo_path, "
            "whatsapp_e164, optin_whatsapp_fecha, created_at "
            "FROM socios WHERE id = %s",
            (member_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row, strict=False))

    def search_by_name(self, search_term: str) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.nombres, s.apellidos,
                   COALESCE(s.photo_path, '') AS photo_path,
                   COUNT(sc.credito_letra) AS creditos
            FROM socios s
            LEFT JOIN socio_credito sc ON s.id = sc.socio_id
            WHERE s.nombres LIKE %s OR s.apellidos LIKE %s
            GROUP BY s.id
            ORDER BY s.nombres
            """,
            (f"%{search_term}%", f"%{search_term}%"),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row, strict=False)) for row in cursor.fetchall()]

    def get_balance(self, member_id: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT saldo FROM socios WHERE id = %s", (member_id,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def save(
        self,
        nombres: str,
        apellidos: str,
        phone: str | None,
        photo_path: str | None,
        saldo: int = 0,
        whatsapp_e164: str | None = None,
        optin_whatsapp_fecha: str | None = None,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO socios (nombres, apellidos, celular, photo_path, saldo,
                                whatsapp_e164, optin_whatsapp_fecha)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (nombres, apellidos, phone, photo_path, saldo, whatsapp_e164, optin_whatsapp_fecha),
        )
        row = cursor.fetchone()
        return int(row[0])

    def update(
        self,
        socio_id: int,
        nombres: str,
        apellidos: str,
        phone: str | None,
        photo_path: str | None,
        nuevo_saldo: int,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE socios SET nombres = %s, apellidos = %s, celular = %s,
                              photo_path = %s, saldo = %s
            WHERE id = %s
            """,
            (nombres, apellidos, phone, photo_path, nuevo_saldo, socio_id),
        )

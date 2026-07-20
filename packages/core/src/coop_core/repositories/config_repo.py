from coop_core.db.connection import DbConnection


class ConfigRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def get(self, key: str) -> str | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = %s", (key,))
        row = cursor.fetchone()
        return str(row["value"]) if row else None

    def get_int(self, key: str) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = %s", (key,))
        row = cursor.fetchone()
        return int(row["value"]) if row else 0

    def set(self, key: str, value: str) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO config (key, value) VALUES (%s, %s)
            ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )

from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.utils.fecha import get_hoy_str


class RetiroService:
    def __init__(
        self,
        conn: DbConnection,
        config: ConfigRepository,
        auxiliar: AuxiliarRepository,
    ) -> None:
        self._conn = conn
        self._config = config
        self._auxiliar = auxiliar

    def register(self, socio_data: dict[str, Any], monto: int) -> dict[str, Any]:
        """
        Lanza ValueError si el saldo del socio es insuficiente.
        Retorna dict con todos los datos del recibo para generación de PDF.
        """
        socio_id = int(socio_data["id"])
        saldo_anterior = int(socio_data["saldo"])

        if monto > saldo_anterior:
            raise ValueError("El socio no tiene saldo suficiente para este retiro.")

        fecha = get_hoy_str()
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO recibos (socio_id) VALUES (%s) RETURNING id",
                (socio_id,),
            )
            recibo_id = int(cursor.fetchone()[0])

            cursor.execute(
                """
                INSERT INTO detalle_recibo (recibo_id, tipo_operacion, socio_id, monto)
                VALUES (%s, 'retiro', %s, %s)
                """,
                (recibo_id, socio_id, monto),
            )
            cursor.execute(
                "UPDATE socios SET saldo = saldo - %s WHERE id = %s",
                (monto, socio_id),
            )

            saldo_caja = self._config.get_int("saldo_en_caja")
            nuevo_saldo_caja = saldo_caja - monto
            self._config.set("saldo_en_caja", str(nuevo_saldo_caja))

            nombre = f"{socio_data['nombres']} {socio_data['apellidos']}"
            self._auxiliar.add(
                fecha=fecha, tipo="Retiro", socio=nombre,
                recibo=recibo_id, monto=-monto, saldo=nuevo_saldo_caja,
            )

            self._conn.commit()

            return {
                "recibo_id": recibo_id,
                "fecha": fecha,
                "socio_id": socio_id,
                "nombres": str(socio_data["nombres"]),
                "apellidos": str(socio_data["apellidos"]),
                "monto": monto,
                "saldo_anterior": saldo_anterior,
                "saldo_nuevo": saldo_anterior - monto,
                "nuevo_saldo_caja": nuevo_saldo_caja,
            }
        except Exception:
            self._conn.rollback()
            raise

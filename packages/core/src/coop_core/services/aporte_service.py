from typing import Any

from coop_core.config.papeleria import PAPELERIA_POR_APORTE, es_cobrable
from coop_core.db.connection import DbConnection
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.utils.fecha import get_hoy_str


class AporteService:
    def __init__(
        self,
        conn: DbConnection,
        config: ConfigRepository,
        auxiliar: AuxiliarRepository,
    ) -> None:
        self._conn = conn
        self._config = config
        self._auxiliar = auxiliar

    def register(
        self,
        recibi_de_id: int,
        aportes: list[dict[str, Any]],
        count_cobrables: int,
    ) -> dict[str, Any]:
        """
        aportes: list of {"socio_data": dict, "monto": int}
        Retorna dict con todos los datos del recibo para generación de PDF.
        """
        fecha = get_hoy_str()
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO recibos (socio_id) VALUES (%s) RETURNING id",
                (recibi_de_id,),
            )
            recibo_id = int(cursor.fetchone()[0])

            saldo_caja = self._config.get_int("saldo_en_caja")
            saldo_admin = self._config.get_int("total_admin")

            aportes_result: list[dict[str, Any]] = []
            for item in aportes:
                socio_data = item["socio_data"]
                monto: int = item["monto"]
                socio_id = int(socio_data["id"])
                saldo_anterior = int(socio_data["saldo"])

                cursor.execute(
                    """
                    INSERT INTO detalle_recibo (recibo_id, tipo_operacion, socio_id, monto)
                    VALUES (%s, 'aporte', %s, %s)
                    """,
                    (recibo_id, socio_id, monto),
                )
                cursor.execute(
                    "UPDATE socios SET saldo = saldo + %s WHERE id = %s",
                    (monto, socio_id),
                )
                saldo_caja += monto
                nombre = f"{socio_data['nombres']} {socio_data['apellidos']}"
                self._auxiliar.add(
                    fecha=fecha, tipo="Aporte", socio=nombre,
                    recibo=recibo_id, monto=monto, saldo=saldo_caja,
                )
                aportes_result.append({
                    "socio_id": socio_id,
                    "nombres": str(socio_data["nombres"]),
                    "apellidos": str(socio_data["apellidos"]),
                    "monto": monto,
                    "saldo_anterior": saldo_anterior,
                    "saldo_nuevo": saldo_anterior + monto,
                    "cobro_papeleria": es_cobrable(socio_id),
                })

            self._config.set("saldo_en_caja", str(saldo_caja))
            self._config.set(
                "total_admin", str(saldo_admin + PAPELERIA_POR_APORTE * count_cobrables)
            )
            self._conn.commit()

            return {
                "recibo_id": recibo_id,
                "fecha": fecha,
                "recibi_de_id": recibi_de_id,
                "aportes": aportes_result,
                "count_cobrables": count_cobrables,
                "nuevo_saldo_caja": saldo_caja,
            }
        except Exception:
            self._conn.rollback()
            raise

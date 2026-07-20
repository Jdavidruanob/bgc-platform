from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.services._pago_ops import execute_pago_op, prepare_abono, prepare_cuotas
from coop_core.utils.fecha import get_hoy, get_hoy_str


class PagoService:
    def __init__(
        self,
        conn: DbConnection,
        liquidaciones: LiquidacionesRepository,
        auxiliar: AuxiliarRepository,
        config: ConfigRepository,
    ) -> None:
        self._conn = conn
        self._liquidaciones = liquidaciones
        self._auxiliar = auxiliar
        self._config = config

    def register(
        self,
        recibi_de_id: int,
        pagos_input: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        pagos_input: list de dicts {socio_data, letra_id, n_cuotas?, abono_capital?}
          - n_cuotas > 0 → modo cuotas manual
          - abono_capital > 0 → modo abono cascada
        Lanza ValueError con mensaje descriptivo para errores de validación.
        """
        tasa_mora = float(self._config.get("porcentaje_mora") or "0.02")
        hoy = get_hoy()
        fecha = get_hoy_str()

        ops_pendientes: list[dict[str, Any]] = []
        pagos_para_recibo: dict[int, dict[str, Any]] = {}

        for item in pagos_input:
            socio_data = item["socio_data"]
            letra_id: int = item["letra_id"]
            n_cuotas: int = item.get("n_cuotas", 0)
            abono_capital: int = item.get("abono_capital", 0)
            nombre_socio = f"{socio_data['nombres']} {socio_data['apellidos']}"

            if n_cuotas > 0 and abono_capital > 0:
                raise ValueError(
                    f"En el pago de {nombre_socio} (Letra {letra_id}) "
                    "seleccione solo una opción: cuotas O abono."
                )
            if n_cuotas == 0 and abono_capital == 0:
                continue

            if letra_id not in pagos_para_recibo:
                saldo_ini = self._liquidaciones.get_current_debt(letra_id)
                pagos_para_recibo[letra_id] = {
                    "socio_data": socio_data,
                    "letra_id": letra_id,
                    "nro_cuotas_pagadas_start": 0,
                    "nro_cuotas_pagadas_end": 0,
                    "valor_capital_consolidado": 0,
                    "interes_consolidado": 0,
                    "mora_consolidada": 0,
                    "saldo_capital_antes_pago": saldo_ini,
                    "saldo_capital_despues_pago": 0,
                }

            if n_cuotas > 0:
                ops_pendientes.append(
                    prepare_cuotas(self._conn, socio_data, letra_id, n_cuotas, hoy, tasa_mora)
                )
            else:
                ops_pendientes.append(
                    prepare_abono(self._liquidaciones, socio_data, letra_id, abono_capital, hoy, tasa_mora)
                )

        if not ops_pendientes:
            raise ValueError("No hay operaciones válidas para registrar.")

        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO recibos (socio_id) VALUES (%s) RETURNING id",
                (recibi_de_id,),
            )
            recibo_id = int(cursor.fetchone()[0])

            saldo_caja = self._config.get_int("saldo_en_caja")
            total_admin = self._config.get_int("total_admin")
            mora_total = 0
            reporte_global: dict[str, list[str]] = {}

            for op in ops_pendientes:
                saldo_caja, mora_total = execute_pago_op(
                    cursor, self._liquidaciones, self._auxiliar,
                    op, recibo_id, fecha, saldo_caja, mora_total,
                    pagos_para_recibo, reporte_global,
                )

            self._config.set("saldo_en_caja", str(saldo_caja))
            if mora_total > 0:
                self._config.set("total_admin", str(total_admin + mora_total))
            self._conn.commit()

            pagos_list = list(pagos_para_recibo.values())
            for p in pagos_list:
                sd = p.pop("socio_data", {})
                p["socio_id"] = int(sd.get("id", 0))
                p["nombres"] = str(sd.get("nombres", ""))
                p["apellidos"] = str(sd.get("apellidos", ""))

            return {
                "recibo_id": recibo_id,
                "fecha": fecha,
                "nuevo_saldo_caja": saldo_caja,
                "pagos": pagos_list,
                "reporte": reporte_global,
            }
        except Exception:
            self._conn.rollback()
            raise

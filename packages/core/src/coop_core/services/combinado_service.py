from typing import Any

from coop_core.config.papeleria import PAPELERIA_POR_APORTE, es_cobrable
from coop_core.db.connection import DbConnection
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.services._pago_ops import execute_pago_op, prepare_abono, prepare_cuotas
from coop_core.utils.fecha import get_hoy, get_hoy_str


class CombinadoService:
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
        aportes_input: list[dict[str, Any]],
        pagos_input: list[dict[str, Any]],
        count_cobrables: int,
    ) -> dict[str, Any]:
        """
        aportes_input: list de dicts {socio_data, monto}
        pagos_input:   list de dicts {socio_data, letra_id, n_cuotas?, abono_capital?}
        Lanza ValueError con mensaje descriptivo para errores de validación.
        """
        if not aportes_input and not pagos_input:
            raise ValueError("No hay operaciones válidas para registrar.")

        tasa_mora = float(self._config.get("porcentaje_mora") or "0.02")
        hoy = get_hoy()
        fecha = get_hoy_str()

        aportes_for_exec: list[dict[str, Any]] = []
        for item in aportes_input:
            socio_data = item["socio_data"]
            monto: int = item["monto"]
            saldo_antes = int(socio_data["saldo"])
            aportes_for_exec.append({
                "socio_data": socio_data,
                "monto": monto,
                "saldo_anterior": saldo_antes,
                "saldo_nuevo": saldo_antes + monto,
            })

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

            aportes_result: list[dict[str, Any]] = []
            for ap in aportes_for_exec:
                sd = ap["socio_data"]
                monto = ap["monto"]
                socio_id = int(sd["id"])
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
                nombre = f"{sd['nombres']} {sd['apellidos']}"
                self._auxiliar.add(
                    fecha=fecha, tipo="Aporte", socio=nombre,
                    monto=monto, saldo=saldo_caja, recibo=recibo_id,
                )
                if nombre not in reporte_global:
                    reporte_global[nombre] = []
                reporte_global[nombre].append(f"Aporte: ${monto}")
                aportes_result.append({
                    "socio_id": socio_id,
                    "nombres": str(sd["nombres"]),
                    "apellidos": str(sd["apellidos"]),
                    "monto": monto,
                    "saldo_anterior": ap["saldo_anterior"],
                    "saldo_nuevo": ap["saldo_nuevo"],
                    "cobro_papeleria": es_cobrable(socio_id),
                })

            for op in ops_pendientes:
                saldo_caja, mora_total = execute_pago_op(
                    cursor, self._liquidaciones, self._auxiliar,
                    op, recibo_id, fecha, saldo_caja, mora_total,
                    pagos_para_recibo, reporte_global,
                )

            monto_papeleria = PAPELERIA_POR_APORTE * count_cobrables
            self._config.set("saldo_en_caja", str(saldo_caja))
            self._config.set(
                "total_admin", str(total_admin + monto_papeleria + mora_total)
            )
            self._conn.commit()

            pagos_list = list(pagos_para_recibo.values())
            for p in pagos_list:
                sd2 = p.pop("socio_data", {})
                p["socio_id"] = int(sd2.get("id", 0))
                p["nombres"] = str(sd2.get("nombres", ""))
                p["apellidos"] = str(sd2.get("apellidos", ""))

            return {
                "recibo_id": recibo_id,
                "fecha": fecha,
                "nuevo_saldo_caja": saldo_caja,
                "aportes": aportes_result,
                "pagos": pagos_list,
                "reporte": reporte_global,
            }
        except Exception:
            self._conn.rollback()
            raise

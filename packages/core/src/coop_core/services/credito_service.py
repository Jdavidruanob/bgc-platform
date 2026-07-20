from datetime import date
from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.services.amortization import build_amortization_schedule
from coop_core.utils.fecha import get_hoy, get_hoy_str


class CreditoService:
    def __init__(
        self,
        conn: DbConnection,
        creditos: CreditosRepository,
        liquidaciones: LiquidacionesRepository,
        auxiliar: AuxiliarRepository,
        config: ConfigRepository,
    ) -> None:
        self._conn = conn
        self._creditos = creditos
        self._liquidaciones = liquidaciones
        self._auxiliar = auxiliar
        self._config = config

    def create(
        self,
        socio_ids: list[int],
        capital: int,
        interes_tasa: float,
        n_cuotas: int,
        socios_data: list[dict[str, Any]],
        fecha_inicio: date | None = None,
    ) -> dict[str, Any]:
        """
        Retorna dict con letra_id, tabla de amortización y datos del crédito.
        Lanza ValueError si los parámetros son inválidos.
        """
        if capital <= 0:
            raise ValueError("El capital del crédito debe ser mayor a cero.")
        if n_cuotas <= 0:
            raise ValueError("El número de cuotas debe ser mayor a cero.")

        hoy_date = fecha_inicio or get_hoy()
        fecha_str = get_hoy_str()

        try:
            letra_id = self._creditos.create(
                socio_ids, capital, interes_tasa, n_cuotas, hoy_date.strftime("%Y-%m-%d")
            )
            cuotas = build_amortization_schedule(letra_id, capital, interes_tasa, n_cuotas, hoy_date)
            self._liquidaciones.save_all(cuotas)

            saldo_actual = self._config.get_int("saldo_en_caja")
            nuevo_saldo_caja = saldo_actual - capital

            nombres_str = ", ".join(
                f"{s['nombres']} {s['apellidos']}" for s in socios_data
            )
            self._auxiliar.add(
                fecha=fecha_str,
                tipo="Nuevo Credito",
                socio=nombres_str,
                recibo=None,
                id_credito=str(letra_id),
                monto=-capital,
                saldo=nuevo_saldo_caja,
                cuota=None,
            )
            self._config.set("saldo_en_caja", str(nuevo_saldo_caja))
            self._conn.commit()

            tabla = [
                {
                    "nro_cuota": int(row[1]),
                    "fecha_vencimiento": str(row[2]),
                    "valor_cuota": int(row[3]),
                    "interes_mes": int(row[4]),
                    "cuota_mensual": int(row[5]),
                    "saldo_capital": int(row[6]),
                }
                for row in cuotas
            ]

            return {
                "letra_id": letra_id,
                "fecha": fecha_str,
                "socios": [
                    {"id": int(s["id"]), "nombres": str(s["nombres"]), "apellidos": str(s["apellidos"])}
                    for s in socios_data
                ],
                "capital": capital,
                "interes": interes_tasa,
                "n_cuotas": n_cuotas,
                "nuevo_saldo_caja": nuevo_saldo_caja,
                "tabla_amortizacion": tabla,
            }
        except Exception:
            self._conn.rollback()
            raise

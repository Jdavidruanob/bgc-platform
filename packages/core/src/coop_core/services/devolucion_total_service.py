"""Devolución/retiro TOTAL de un socio.

A diferencia del retiro parcial, esta operación cierra la cuenta del socio:
le devuelve todo su saldo, lo descuenta de la caja y lo retira de la
cooperativa (soft-delete: se marca inactivo, se conserva su historial).

Valida antes de tocar nada (ver ADR de operaciones): saldo > 0, sin créditos
activos y caja suficiente. Si algo no cuadra, lanza ValueError y no modifica
la base.
"""

from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.socios_repo import SociosRepository
from coop_core.utils.fecha import get_hoy_str


class DevolucionTotalService:
    def __init__(
        self,
        conn: DbConnection,
        config: ConfigRepository,
        auxiliar: AuxiliarRepository,
        socios: SociosRepository,
        creditos: CreditosRepository,
    ) -> None:
        self._conn = conn
        self._config = config
        self._auxiliar = auxiliar
        self._socios = socios
        self._creditos = creditos

    def register(self, socio_data: dict[str, Any]) -> dict[str, Any]:
        """Cierra la cuenta del socio devolviéndole todo su saldo.

        Lanza ValueError si: el socio no tiene saldo, tiene créditos activos, o
        la caja no alcanza para devolver el saldo.
        """
        socio_id = int(socio_data["id"])
        saldo = int(socio_data["saldo"])

        if saldo <= 0:
            raise ValueError("El socio no tiene saldo para devolver.")

        activos = self._creditos.find_active_by_socio_id(socio_id)
        if activos:
            letras = ", ".join(str(c["letra"]) for c in activos)
            raise ValueError(
                f"El socio tiene créditos activos (letra {letras}); primero deben quedar "
                "saldados antes de la devolución total."
            )

        saldo_caja = self._config.get_int("saldo_en_caja")
        if saldo > saldo_caja:
            raise ValueError("La caja no tiene suficiente dinero para devolver el saldo del socio.")

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
                VALUES (%s, 'devolucion_total', %s, %s)
                """,
                (recibo_id, socio_id, saldo),
            )

            nuevo_saldo_caja = saldo_caja - saldo
            self._config.set("saldo_en_caja", str(nuevo_saldo_caja))

            # Soft-delete: el saldo queda en 0 y el socio se marca inactivo.
            self._socios.deactivate(socio_id)

            nombre = f"{socio_data['nombres']} {socio_data['apellidos']}"
            self._auxiliar.add(
                fecha=fecha,
                tipo="Devolución total",
                socio=nombre,
                recibo=recibo_id,
                monto=-saldo,
                saldo=nuevo_saldo_caja,
            )

            self._conn.commit()

            return {
                "recibo_id": recibo_id,
                "fecha": fecha,
                "socio_id": socio_id,
                "nombres": str(socio_data["nombres"]),
                "apellidos": str(socio_data["apellidos"]),
                "monto": saldo,
                "nuevo_saldo_caja": nuevo_saldo_caja,
            }
        except Exception:
            self._conn.rollback()
            raise

from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.recibos_repo import RecibosRepository
from coop_core.utils.fecha import get_hoy_str


class CajaService:
    def __init__(
        self,
        config: ConfigRepository,
        auxiliar: AuxiliarRepository,
        recibos: RecibosRepository | None = None,
    ) -> None:
        self._config = config
        self._auxiliar = auxiliar
        self._recibos = recibos

    def get_saldo_caja(self) -> int:
        return self._config.get_int("saldo_en_caja")

    def get_papeleria(self) -> int:
        """Fondo de papelería acumulado (config 'total_admin')."""
        return self._config.get_int("total_admin")

    # Alias histórico: en el software original 'total_admin' guardaba solo la
    # papelería. Se mantiene por compatibilidad.
    def get_total_admin(self) -> int:
        return self.get_papeleria()

    def get_mora_acumulada(self) -> int:
        """Total de abonos por mora cobrados a lo largo del tiempo."""
        if self._recibos is None:
            return 0
        return self._recibos.sum_abono_mora()

    def get_administracion_total(self) -> int:
        """Administración = papelería + mora acumulada (como el BGC-software)."""
        return self.get_papeleria() + self.get_mora_acumulada()

    def get_porcentaje_mora(self) -> float:
        value = self._config.get("porcentaje_mora")
        return float(value) if value else 0.02

    def adjust_caja(self, monto_ajuste: int, motivo: str, nuevo_saldo: int) -> None:
        self._config.set("saldo_en_caja", str(nuevo_saldo))
        self._auxiliar.add(
            fecha=get_hoy_str(),
            tipo=motivo,
            socio="Administracion",
            recibo=None,
            monto=monto_ajuste,
            saldo=nuevo_saldo,
            cuota=None,
            id_credito=None,
        )

    def set_admin_config(self, new_papeleria: int, new_mora: float) -> None:
        self._config.set("total_admin", str(new_papeleria))
        self._config.set("porcentaje_mora", str(new_mora))

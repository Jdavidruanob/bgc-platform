from datetime import date
from typing import Any

from coop_core.services.caja_service import CajaService
from coop_core.utils import fecha as fecha_mod


def _make_service(repos: dict[str, Any]) -> CajaService:
    return CajaService(repos["config"], repos["auxiliar"])


def test_get_saldo_inicial(repos: dict[str, Any]) -> None:
    assert _make_service(repos).get_saldo_caja() == 0


def test_get_porcentaje_mora_default(repos: dict[str, Any]) -> None:
    assert _make_service(repos).get_porcentaje_mora() == 0.02


def test_adjust_caja(repos: dict[str, Any]) -> None:
    fecha_mod.set_fecha_simulada(date(2024, 5, 1))
    repos["config"].set("saldo_en_caja", "1000000")
    repos["conn"].commit()

    svc = _make_service(repos)
    svc.adjust_caja(monto_ajuste=50000, motivo="Ajuste manual", nuevo_saldo=1050000)
    repos["conn"].commit()

    assert svc.get_saldo_caja() == 1050000
    fecha_mod.reset_fecha_normal()


def test_set_admin_config(repos: dict[str, Any]) -> None:
    svc = _make_service(repos)
    svc.set_admin_config(new_papeleria=15000, new_mora=0.03)
    repos["conn"].commit()
    assert svc.get_total_admin() == 15000
    assert svc.get_porcentaje_mora() == 0.03

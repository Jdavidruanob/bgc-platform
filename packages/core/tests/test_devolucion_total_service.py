from datetime import date
from typing import Any

import pytest
from coop_core.services.amortization import build_amortization_schedule
from coop_core.services.devolucion_total_service import DevolucionTotalService


def _make_service(repos: dict[str, Any]) -> DevolucionTotalService:
    return DevolucionTotalService(
        repos["conn"], repos["config"], repos["auxiliar"], repos["socios"], repos["creditos"]
    )


def _insert_socio(repos: dict[str, Any], nombres: str, apellidos: str, saldo: int) -> int:
    return repos["socios"].save(nombres, apellidos, None, None, saldo)


def _set_caja(repos: dict[str, Any], monto: int) -> None:
    repos["config"].set("saldo_en_caja", str(monto))
    repos["conn"].commit()


def _socio_data(repos: dict[str, Any], socio_id: int, saldo: int) -> dict[str, Any]:
    return {"id": socio_id, "nombres": "Harvey", "apellidos": "Ramos", "saldo": saldo}


def test_devolucion_total_exitosa(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Harvey", "Ramos", saldo=300000)
    _set_caja(repos, 500000)

    result = _make_service(repos).register(_socio_data(repos, socio_id, 300000))

    assert result["monto"] == 300000
    assert result["nuevo_saldo_caja"] == 200000
    # El socio queda inactivo y con saldo 0: no aparece en listados/búsqueda.
    assert repos["socios"].find_all() == []
    assert repos["socios"].search_by_name("Harvey") == []
    assert repos["config"].get_int("saldo_en_caja") == 200000
    # Pero la fila sigue existiendo (soft-delete), consultable por id.
    assert repos["socios"].find_by_id(socio_id) is not None


def test_devolucion_total_sin_saldo(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Sin", "Saldo", saldo=0)
    _set_caja(repos, 500000)
    with pytest.raises(ValueError, match="no tiene saldo"):
        _make_service(repos).register(_socio_data(repos, socio_id, 0))


def test_devolucion_total_caja_insuficiente(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Harvey", "Ramos", saldo=300000)
    _set_caja(repos, 100000)
    with pytest.raises(ValueError, match="caja no tiene suficiente"):
        _make_service(repos).register(_socio_data(repos, socio_id, 300000))


def test_devolucion_total_con_credito_activo(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Harvey", "Ramos", saldo=300000)
    _set_caja(repos, 500000)
    # Crédito con cuotas pendientes → bloquea la devolución total.
    letra = repos["creditos"].create([socio_id], 600000, 0.02, 6, "2024-01-01")
    repos["liquidaciones"].save_all(build_amortization_schedule(letra, 600000, 0.02, 6, date(2024, 1, 1)))
    repos["conn"].commit()

    with pytest.raises(ValueError, match="créditos activos"):
        _make_service(repos).register(_socio_data(repos, socio_id, 300000))

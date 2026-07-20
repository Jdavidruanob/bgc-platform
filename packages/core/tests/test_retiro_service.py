from typing import Any

import pytest

from coop_core.services.retiro_service import RetiroService


def _make_service(repos: dict[str, Any]) -> RetiroService:
    return RetiroService(repos["conn"], repos["config"], repos["auxiliar"])


def _insert_socio(repos: dict[str, Any], nombres: str, apellidos: str, saldo: int = 0) -> int:
    return repos["socios"].save(nombres, apellidos, None, None, saldo)


def _set_caja(repos: dict[str, Any], monto: int) -> None:
    repos["config"].set("saldo_en_caja", str(monto))
    repos["conn"].commit()


def test_retiro_exitoso(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Ana", "Gomez", saldo=200000)
    _set_caja(repos, 500000)
    socio_data = {"id": socio_id, "nombres": "Ana", "apellidos": "Gomez", "saldo": 200000}

    result = _make_service(repos).register(socio_data, 80000)

    assert result["recibo_id"] == 1
    assert result["saldo_nuevo"] == 120000
    assert result["nuevo_saldo_caja"] == 420000
    assert repos["socios"].get_balance(socio_id) == 120000
    assert repos["config"].get_int("saldo_en_caja") == 420000


def test_retiro_saldo_insuficiente(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Luis", "Paz", saldo=50000)
    socio_data = {"id": socio_id, "nombres": "Luis", "apellidos": "Paz", "saldo": 50000}

    with pytest.raises(ValueError, match="saldo suficiente"):
        _make_service(repos).register(socio_data, 100000)


def test_retiro_saldo_exacto(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Clara", "Rios", saldo=100000)
    _set_caja(repos, 200000)
    socio_data = {"id": socio_id, "nombres": "Clara", "apellidos": "Rios", "saldo": 100000}

    result = _make_service(repos).register(socio_data, 100000)
    assert result["saldo_nuevo"] == 0

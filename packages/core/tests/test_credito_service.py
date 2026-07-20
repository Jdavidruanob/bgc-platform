from datetime import date
from typing import Any

import pytest

from coop_core.services.credito_service import CreditoService


def _make_service(repos: dict[str, Any]) -> CreditoService:
    return CreditoService(
        repos["conn"],
        repos["creditos"],
        repos["liquidaciones"],
        repos["auxiliar"],
        repos["config"],
    )


def _insert_socio(repos: dict[str, Any], nombres: str, apellidos: str) -> int:
    return repos["socios"].save(nombres, apellidos, None, None)


def _set_caja(repos: dict[str, Any], monto: int) -> None:
    repos["config"].set("saldo_en_caja", str(monto))
    repos["conn"].commit()


def test_crear_credito_basico(repos: dict[str, Any]) -> None:
    _set_caja(repos, 2_000_000)
    sid = _insert_socio(repos, "Pedro", "Castillo")
    socios_data = [{"id": sid, "nombres": "Pedro", "apellidos": "Castillo"}]

    result = _make_service(repos).create(
        socio_ids=[sid],
        capital=1_200_000,
        interes_tasa=0.02,
        n_cuotas=12,
        socios_data=socios_data,
        fecha_inicio=date(2024, 1, 1),
    )

    assert result["letra_id"] == 1
    assert result["capital"] == 1_200_000
    assert result["nuevo_saldo_caja"] == 800_000
    assert len(result["tabla_amortizacion"]) == 12
    total_cap = sum(r["valor_cuota"] for r in result["tabla_amortizacion"])
    assert total_cap == 1_200_000


def test_credito_descuenta_caja(repos: dict[str, Any]) -> None:
    _set_caja(repos, 1_000_000)
    sid = _insert_socio(repos, "Luisa", "Vargas")
    _make_service(repos).create(
        socio_ids=[sid],
        capital=400_000,
        interes_tasa=0.015,
        n_cuotas=4,
        socios_data=[{"id": sid, "nombres": "Luisa", "apellidos": "Vargas"}],
        fecha_inicio=date(2024, 1, 1),
    )
    assert repos["config"].get_int("saldo_en_caja") == 600_000


def test_credito_capital_cero_lanza_error(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "X", "Y")
    with pytest.raises(ValueError):
        _make_service(repos).create(
            socio_ids=[sid], capital=0, interes_tasa=0.02, n_cuotas=12,
            socios_data=[{"id": sid, "nombres": "X", "apellidos": "Y"}],
        )


def test_credito_cuotas_cero_lanza_error(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "X", "Y")
    with pytest.raises(ValueError):
        _make_service(repos).create(
            socio_ids=[sid], capital=100_000, interes_tasa=0.02, n_cuotas=0,
            socios_data=[{"id": sid, "nombres": "X", "apellidos": "Y"}],
        )


def test_tabla_amortizacion_montos_enteros(repos: dict[str, Any]) -> None:
    _set_caja(repos, 2_000_000)
    sid = _insert_socio(repos, "Carlos", "Mesa")
    result = _make_service(repos).create(
        socio_ids=[sid], capital=750_000, interes_tasa=0.02, n_cuotas=6,
        socios_data=[{"id": sid, "nombres": "Carlos", "apellidos": "Mesa"}],
        fecha_inicio=date(2024, 1, 1),
    )
    for row in result["tabla_amortizacion"]:
        assert isinstance(row["valor_cuota"], int)
        assert isinstance(row["interes_mes"], int)
        assert isinstance(row["cuota_mensual"], int)
        assert isinstance(row["saldo_capital"], int)

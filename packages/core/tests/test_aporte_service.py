from typing import Any

import pytest

from coop_core.services.aporte_service import AporteService
from coop_core.utils import fecha as fecha_mod


def _make_service(repos: dict[str, Any]) -> AporteService:
    return AporteService(repos["conn"], repos["config"], repos["auxiliar"])


def _insert_socio(repos: dict[str, Any], nombres: str, apellidos: str, saldo: int = 0) -> int:
    return repos["socios"].save(nombres, apellidos, None, None, saldo)


def test_aporte_simple(repos: dict[str, Any]) -> None:
    fecha_mod.set_fecha_simulada(__import__("datetime").date(2024, 3, 1))
    socio_id = _insert_socio(repos, "Ana", "Garcia", saldo=0)
    socio_data = {"id": socio_id, "nombres": "Ana", "apellidos": "Garcia", "saldo": 0}

    service = _make_service(repos)
    result = service.register(
        recibi_de_id=socio_id,
        aportes=[{"socio_data": socio_data, "monto": 50000}],
        count_cobrables=1,
    )

    assert result["recibo_id"] == 1
    assert result["aportes"][0]["saldo_nuevo"] == 50000
    assert result["nuevo_saldo_caja"] == 50000

    # Verify DB state
    saldo_db = repos["socios"].get_balance(socio_id)
    assert saldo_db == 50000
    saldo_caja = repos["config"].get_int("saldo_en_caja")
    assert saldo_caja == 50000
    fecha_mod.reset_fecha_normal()


def test_aporte_actualiza_admin(repos: dict[str, Any]) -> None:
    socio_id = _insert_socio(repos, "Luis", "Mora")
    socio_data = {"id": socio_id, "nombres": "Luis", "apellidos": "Mora", "saldo": 0}
    service = _make_service(repos)
    service.register(
        recibi_de_id=socio_id,
        aportes=[{"socio_data": socio_data, "monto": 100000}],
        count_cobrables=1,
    )
    admin = repos["config"].get_int("total_admin")
    assert admin == 3000  # PAPELERIA_POR_APORTE * 1


def test_aporte_multiples_socios(repos: dict[str, Any]) -> None:
    id1 = _insert_socio(repos, "Pedro", "Lopez")
    id2 = _insert_socio(repos, "Maria", "Ruiz")
    s1 = {"id": id1, "nombres": "Pedro", "apellidos": "Lopez", "saldo": 0}
    s2 = {"id": id2, "nombres": "Maria", "apellidos": "Ruiz", "saldo": 0}

    service = _make_service(repos)
    result = service.register(
        recibi_de_id=id1,
        aportes=[
            {"socio_data": s1, "monto": 50000},
            {"socio_data": s2, "monto": 30000},
        ],
        count_cobrables=2,
    )
    assert result["nuevo_saldo_caja"] == 80000
    assert repos["socios"].get_balance(id1) == 50000
    assert repos["socios"].get_balance(id2) == 30000


def test_aporte_rollback_on_error(repos: dict[str, Any]) -> None:
    """Si la DB falla a mitad, no se persiste nada."""
    socio_id = _insert_socio(repos, "Error", "Test")
    socio_data = {"id": socio_id, "nombres": "Error", "apellidos": "Test", "saldo": 0}
    service = _make_service(repos)

    # Provide non-existent socio_id in second aporte to trigger FK violation
    bad_data = {"id": 9999, "nombres": "X", "apellidos": "Y", "saldo": 0}
    with pytest.raises(Exception):
        service.register(
            recibi_de_id=socio_id,
            aportes=[
                {"socio_data": socio_data, "monto": 10000},
                {"socio_data": bad_data, "monto": 5000},
            ],
            count_cobrables=2,
        )
    # Saldo de caja no debe haber cambiado
    assert repos["config"].get_int("saldo_en_caja") == 0

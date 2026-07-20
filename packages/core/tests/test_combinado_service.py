from datetime import date
from typing import Any

import pytest

from coop_core.services.combinado_service import CombinadoService
from coop_core.services.credito_service import CreditoService
from coop_core.utils import fecha as fecha_mod


def _make_service(repos: dict[str, Any]) -> CombinadoService:
    return CombinadoService(repos["conn"], repos["liquidaciones"], repos["auxiliar"], repos["config"])


def _make_credito(repos: dict[str, Any]) -> CreditoService:
    return CreditoService(
        repos["conn"], repos["creditos"], repos["liquidaciones"], repos["auxiliar"], repos["config"]
    )


def _insert_socio(repos: dict[str, Any], nombres: str, apellidos: str, saldo: int = 0) -> int:
    return repos["socios"].save(nombres, apellidos, None, None, saldo)


def _setup_credito(repos: dict[str, Any], sid: int, capital: int, n_cuotas: int) -> int:
    repos["config"].set("saldo_en_caja", str(capital + 500_000))
    repos["conn"].commit()
    result = _make_credito(repos).create(
        socio_ids=[sid], capital=capital, interes_tasa=0.02,
        n_cuotas=n_cuotas, socios_data=[{"id": sid, "nombres": "T", "apellidos": "S"}],
        fecha_inicio=date(2024, 1, 1),
    )
    return int(result["letra_id"])


def test_combinado_aporte_y_pago(repos: dict[str, Any]) -> None:
    fecha_mod.set_fecha_simulada(date(2024, 4, 1))
    repos["config"].set("saldo_en_caja", "500000")
    repos["conn"].commit()

    sid = _insert_socio(repos, "Julia", "Reyes", saldo=0)
    letra = _setup_credito(repos, sid, 600_000, 6)

    sd = {"id": sid, "nombres": "Julia", "apellidos": "Reyes", "saldo": 0}

    result = _make_service(repos).register(
        recibi_de_id=sid,
        aportes_input=[{"socio_data": sd, "monto": 50_000}],
        pagos_input=[{"socio_data": sd, "letra_id": letra, "n_cuotas": 1}],
        count_cobrables=1,
    )

    assert result["recibo_id"] is not None
    assert len(result["aportes"]) == 1
    assert len(result["pagos"]) == 1
    assert result["aportes"][0]["saldo_nuevo"] == 50_000
    fecha_mod.reset_fecha_normal()


def test_combinado_sin_operaciones_lanza_error(repos: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="No hay operaciones"):
        _make_service(repos).register(
            recibi_de_id=1,
            aportes_input=[],
            pagos_input=[],
            count_cobrables=0,
        )

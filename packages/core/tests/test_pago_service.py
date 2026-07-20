from datetime import date
from typing import Any

import pytest

from coop_core.services.amortization import calculate_mora
from coop_core.services.credito_service import CreditoService
from coop_core.services.pago_service import PagoService
from coop_core.utils import fecha as fecha_mod


def _make_pago(repos: dict[str, Any]) -> PagoService:
    return PagoService(repos["conn"], repos["liquidaciones"], repos["auxiliar"], repos["config"])


def _make_credito(repos: dict[str, Any]) -> CreditoService:
    return CreditoService(
        repos["conn"], repos["creditos"], repos["liquidaciones"], repos["auxiliar"], repos["config"]
    )


def _insert_socio(repos: dict[str, Any], nombres: str, apellidos: str) -> int:
    return repos["socios"].save(nombres, apellidos, None, None)


def _setup_credito(repos: dict[str, Any], sid: int, capital: int, n_cuotas: int) -> int:
    repos["config"].set("saldo_en_caja", str(capital + 500_000))
    repos["conn"].commit()
    sd = [{"id": sid, "nombres": "Test", "apellidos": "Socio"}]
    result = _make_credito(repos).create(
        socio_ids=[sid], capital=capital, interes_tasa=0.02,
        n_cuotas=n_cuotas, socios_data=sd, fecha_inicio=date(2024, 1, 1),
    )
    return int(result["letra_id"])


def test_pago_cuotas_manual(repos: dict[str, Any]) -> None:
    fecha_mod.set_fecha_simulada(date(2024, 4, 1))
    sid = _insert_socio(repos, "Maria", "Lopez")
    letra = _setup_credito(repos, sid, 600_000, 6)
    sd = {"id": sid, "nombres": "Maria", "apellidos": "Lopez"}

    saldo_antes = repos["config"].get_int("saldo_en_caja")
    result = _make_pago(repos).register(
        recibi_de_id=sid,
        pagos_input=[{"socio_data": sd, "letra_id": letra, "n_cuotas": 2}],
    )

    assert result["recibo_id"] is not None
    assert result["pagos"][0]["valor_capital_consolidado"] > 0
    assert repos["config"].get_int("saldo_en_caja") > saldo_antes
    fecha_mod.reset_fecha_normal()


def test_pago_sin_operaciones_validas(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "X", "Y")
    sd = {"id": sid, "nombres": "X", "apellidos": "Y"}
    with pytest.raises(ValueError, match="No hay operaciones"):
        _make_pago(repos).register(
            recibi_de_id=sid,
            pagos_input=[{"socio_data": sd, "letra_id": 99, "n_cuotas": 0, "abono_capital": 0}],
        )


def test_pago_cuotas_y_abono_a_la_vez_lanza_error(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "A", "B")
    letra = _setup_credito(repos, sid, 600_000, 6)
    sd = {"id": sid, "nombres": "A", "apellidos": "B"}
    with pytest.raises(ValueError, match="solo una opción"):
        _make_pago(repos).register(
            recibi_de_id=sid,
            pagos_input=[{"socio_data": sd, "letra_id": letra, "n_cuotas": 1, "abono_capital": 100000}],
        )


def test_pago_cuotas_insuficientes(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "C", "D")
    letra = _setup_credito(repos, sid, 300_000, 3)
    sd = {"id": sid, "nombres": "C", "apellidos": "D"}
    with pytest.raises(ValueError, match="suficientes cuotas"):
        _make_pago(repos).register(
            recibi_de_id=sid,
            pagos_input=[{"socio_data": sd, "letra_id": letra, "n_cuotas": 10}],
        )


def test_pago_abono_insuficiente_primera_cuota(repos: dict[str, Any]) -> None:
    """Abono menor que la primera cuota vencida → ValueError (pagables == 0)."""
    fecha_mod.set_fecha_simulada(date(2024, 2, 15))  # cuota 1 (2024-02-01) vencida
    sid = _insert_socio(repos, "E", "F")
    letra = _setup_credito(repos, sid, 600_000, 6)
    sd = {"id": sid, "nombres": "E", "apellidos": "F"}
    with pytest.raises(ValueError, match="Abono insuficiente"):
        _make_pago(repos).register(
            recibi_de_id=sid,
            pagos_input=[{"socio_data": sd, "letra_id": letra, "abono_capital": 100}],
        )
    fecha_mod.reset_fecha_normal()


def test_pago_abono_incompleto_segunda_cuota(repos: dict[str, Any]) -> None:
    """Abono cubre primera cuota vencida pero no la segunda → ValueError (pagables > 0)."""
    hoy_test = date(2024, 3, 15)  # cuotas 1 (2024-02-01) y 2 (2024-03-01) vencidas
    fecha_mod.set_fecha_simulada(hoy_test)
    sid = _insert_socio(repos, "I", "J")
    letra = _setup_credito(repos, sid, 600_000, 6)
    pending = repos["liquidaciones"].find_pending(letra)
    cuota1 = pending[0]
    # Include mora so the abono covers cuota 1's full costo but not cuota 2
    mora1 = calculate_mora(str(cuota1["fecha_vencimiento"]), hoy_test, int(cuota1["valor_cuota"]), 0.02)
    costo_cuota1 = int(cuota1["valor_cuota"]) + int(cuota1["interes_mes"]) + mora1
    abono = costo_cuota1 + 500  # covers cuota 1 fully, leftover 500 << cuota 2 cost
    sd = {"id": sid, "nombres": "I", "apellidos": "J"}
    with pytest.raises(ValueError, match="Abono incompleto"):
        _make_pago(repos).register(
            recibi_de_id=sid,
            pagos_input=[{"socio_data": sd, "letra_id": letra, "abono_capital": abono}],
        )
    fecha_mod.reset_fecha_normal()


def test_pago_abono_cascada_exitoso(repos: dict[str, Any]) -> None:
    """Abono cubre cuota vencida + remanente va como abono capital."""
    fecha_mod.set_fecha_simulada(date(2024, 2, 15))  # solo cuota 1 (2024-02-01) vencida
    sid = _insert_socio(repos, "G", "H")
    letra = _setup_credito(repos, sid, 600_000, 6)
    pending = repos["liquidaciones"].find_pending(letra)
    cuota1 = pending[0]
    # Mora=0 porque hoy(2024-02-15) < f_limite(2024-03-01)
    costo_cuota1 = int(cuota1["valor_cuota"]) + int(cuota1["interes_mes"])
    abono = costo_cuota1 + 10_000  # 10_000 extra va como abono capital

    sd = {"id": sid, "nombres": "G", "apellidos": "H"}
    result = _make_pago(repos).register(
        recibi_de_id=sid,
        pagos_input=[{"socio_data": sd, "letra_id": letra, "abono_capital": abono}],
    )
    assert result["recibo_id"] is not None
    assert result["pagos"][0]["valor_capital_consolidado"] > 0
    fecha_mod.reset_fecha_normal()

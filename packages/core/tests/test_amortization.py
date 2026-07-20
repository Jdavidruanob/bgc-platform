from datetime import date

from coop_core.services.amortization import (
    build_amortization_schedule,
    calculate_mora,
    round_installments,
)


def test_calculate_mora_dentro_gracia() -> None:
    assert calculate_mora("2024-01-01", date(2024, 1, 15), 100000, 0.02) == 0


def test_calculate_mora_fuera_gracia() -> None:
    mora = calculate_mora("2024-01-01", date(2024, 3, 1), 100000, 0.02)
    assert mora == 2000


def test_round_installments_divides_exactly() -> None:
    cuota_base, cuota_final = round_installments(1_200_000, 12)
    assert cuota_base * 11 + cuota_final == 1_200_000
    assert cuota_final >= 10000


def test_build_amortization_schedule_suma_capital() -> None:
    rows = build_amortization_schedule(1, 1_200_000, 0.02, 12, date(2024, 1, 1))
    assert len(rows) == 12
    total_capital = sum(int(r[3]) for r in rows)
    assert total_capital == 1_200_000


def test_build_amortization_saldo_llega_a_cero() -> None:
    rows = build_amortization_schedule(1, 500_000, 0.015, 5, date(2024, 1, 1))
    assert int(rows[-1][6]) == 0  # saldo_capital de la última cuota


def test_build_amortization_fechas_mensuales() -> None:
    rows = build_amortization_schedule(1, 300_000, 0.02, 3, date(2024, 1, 1))
    assert rows[0][2] == "2024-02-01"
    assert rows[1][2] == "2024-03-01"
    assert rows[2][2] == "2024-04-01"


def test_montos_son_enteros() -> None:
    rows = build_amortization_schedule(1, 750_000, 0.02, 6, date(2024, 1, 1))
    for row in rows:
        for val in row[3:]:  # valor_cuota, interes_mes, cuota_mensual, saldo_capital
            if isinstance(val, (int, float)):
                assert isinstance(val, int), f"Valor no entero: {val}"

from datetime import date

from coop_core.utils import fecha as mod


def test_get_hoy_returns_today() -> None:
    mod.reset_fecha_normal()
    assert mod.get_hoy() == date.today()


def test_set_fecha_simulada() -> None:
    target = date(2024, 6, 15)
    mod.set_fecha_simulada(target)
    assert mod.get_hoy() == target
    assert mod.get_hoy_str() == "2024-06-15"
    mod.reset_fecha_normal()


def test_reset_restores_today() -> None:
    mod.set_fecha_simulada(date(2020, 1, 1))
    mod.reset_fecha_normal()
    assert mod.get_hoy() == date.today()

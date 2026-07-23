import coop_core.config.papeleria as mod
import pytest


def test_socios_no_exentos_son_cobrables() -> None:
    # Los IDs 1-5 son exentos (tesorero y familia); el resto sí paga.
    assert mod.es_cobrable(999) is True
    assert mod.es_cobrable(100) is True


def test_socios_exentos_configurados_no_son_cobrables() -> None:
    for sid in (1, 2, 3, 4, 5):
        assert mod.es_cobrable(sid) is False


def test_count_cobrables_excluye_exentos() -> None:
    # 1 y 2 exentos, 100 y 999 cobrables
    assert mod.count_cobrables([1, 2, 100, 999]) == 2


def test_exento_not_cobrable(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(mod, "SOCIOS_EXENTOS_PAPELERIA", frozenset({5}))
    assert mod.es_cobrable(5) is False
    assert mod.es_cobrable(6) is True


def test_count_with_exento(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(mod, "SOCIOS_EXENTOS_PAPELERIA", frozenset({1}))
    assert mod.count_cobrables([1, 2, 3]) == 2

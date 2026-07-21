import coop_core.config.papeleria as mod
import pytest


def test_all_cobrables_by_default() -> None:
    assert mod.es_cobrable(1) is True
    assert mod.es_cobrable(999) is True


def test_count_cobrables_all() -> None:
    assert mod.count_cobrables([1, 2, 3]) == 3


def test_exento_not_cobrable(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(mod, "SOCIOS_EXENTOS_PAPELERIA", frozenset({5}))
    assert mod.es_cobrable(5) is False
    assert mod.es_cobrable(6) is True


def test_count_with_exento(monkeypatch: "pytest.MonkeyPatch") -> None:
    monkeypatch.setattr(mod, "SOCIOS_EXENTOS_PAPELERIA", frozenset({1}))
    assert mod.count_cobrables([1, 2, 3]) == 2

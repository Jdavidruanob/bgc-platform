"""Tests unitarios del freno anti-bucle del asistente."""

from __future__ import annotations

from coop_api.asistente.limite import LimitadorRespuestas


def _con_reloj(lim: LimitadorRespuestas, t: list[float]) -> LimitadorRespuestas:
    lim._ahora = lambda: t[0]  # type: ignore[method-assign]  # reloj controlado por el test
    return lim


def test_libera_cupo_al_pasar_la_ventana() -> None:
    t = [0.0]
    lim = _con_reloj(LimitadorRespuestas(max_respuestas=2, ventana_segundos=60), t)
    assert lim.permitir("+57300")
    assert lim.permitir("+57300")
    assert not lim.permitir("+57300")
    t[0] = 61.0
    assert lim.permitir("+57300")


def test_wamid_vacio_nunca_cuenta_como_visto() -> None:
    lim = LimitadorRespuestas()
    assert not lim.ya_visto("")
    assert not lim.ya_visto("")


def test_wamids_viejos_se_olvidan() -> None:
    from coop_api.asistente import limite

    lim = LimitadorRespuestas()
    for i in range(limite._MAX_WAMIDS + 1):
        lim.ya_visto(f"w{i}")
    assert not lim.ya_visto("w0")
    assert lim.ya_visto(f"w{limite._MAX_WAMIDS}")

from datetime import date, timedelta
from typing import Any


def _crear_credito(repos: dict[str, Any], vencimientos: list[tuple[int, str]]) -> int:
    """Crea un crédito con una cuota por cada (nro_cuota, fecha_vencimiento)."""
    sid = repos["socios"].save("Pedro", "Castillo", None, None)
    letra_id = repos["creditos"].create([sid], 1_000_000, 0.02, len(vencimientos), "2024-01-01")
    repos["creditos"].save_amortization(
        [(letra_id, nro, fecha, 100_000, 2_000, 102_000, 500_000) for nro, fecha in vencimientos]
    )
    return letra_id


def test_find_cuotas_por_avisar_mora_incluye_la_que_vence_hoy(repos: dict[str, Any]) -> None:
    hoy = date(2026, 8, 13)
    letra_id = _crear_credito(repos, [(1, hoy.strftime("%Y-%m-%d"))])

    encontradas = repos["liquidaciones"].find_cuotas_por_avisar_mora(hoy, 5)

    assert {c["nro_cuota"] for c in encontradas} == {1}
    assert encontradas[0]["credito_letra"] == letra_id


def test_find_cuotas_por_avisar_mora_incluye_barrido_inicial_dentro_de_gracia(repos: dict[str, Any]) -> None:
    """Cuotas que vencieron hace pocos días (aún dentro de los días de
    gracia) también se avisan la primera vez que corre el job."""
    hoy = date(2026, 8, 13)
    _crear_credito(repos, [(1, (hoy - timedelta(days=4)).strftime("%Y-%m-%d"))])

    encontradas = repos["liquidaciones"].find_cuotas_por_avisar_mora(hoy, 5)

    assert len(encontradas) == 1


def test_find_cuotas_por_avisar_mora_excluye_las_que_ya_entraron_en_mora(repos: dict[str, Any]) -> None:
    hoy = date(2026, 8, 13)
    _crear_credito(repos, [(1, (hoy - timedelta(days=5)).strftime("%Y-%m-%d"))])

    encontradas = repos["liquidaciones"].find_cuotas_por_avisar_mora(hoy, 5)

    assert encontradas == []


def test_find_cuotas_por_avisar_mora_excluye_cuotas_que_aun_no_vencen(repos: dict[str, Any]) -> None:
    hoy = date(2026, 8, 13)
    _crear_credito(repos, [(1, (hoy + timedelta(days=1)).strftime("%Y-%m-%d"))])

    encontradas = repos["liquidaciones"].find_cuotas_por_avisar_mora(hoy, 5)

    assert encontradas == []


def test_find_cuotas_por_avisar_mora_excluye_cuotas_ya_avisadas(repos: dict[str, Any]) -> None:
    hoy = date(2026, 8, 13)
    _crear_credito(repos, [(1, hoy.strftime("%Y-%m-%d"))])
    cuota_id = repos["liquidaciones"].find_cuotas_por_avisar_mora(hoy, 5)[0]["id"]

    repos["liquidaciones"].marcar_notif_prev_enviada(cuota_id)

    assert repos["liquidaciones"].find_cuotas_por_avisar_mora(hoy, 5) == []

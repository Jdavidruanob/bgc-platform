from unittest.mock import AsyncMock

from coop_bot.api.cliente import ApiClient
from coop_bot.dialogo.entidades import (
    formatear_lista_letras,
    formatear_lista_socios,
    parsear_seleccion,
    resolver_letra,
    resolver_socio,
)
from coop_contracts.respuestas import CreditoResumen, CreditosResponse, SocioSearchItem

# ── resolver_socio contra el mock real ───────────────────────────────────────


async def test_resolver_socio_sin_resultados(api_client: ApiClient) -> None:
    resolucion = await resolver_socio(api_client, "nombre-que-no-existe-en-el-mock")
    assert resolucion.estado == "no_encontrado"
    assert resolucion.resuelto is None


async def test_resolver_socio_un_resultado(api_client: ApiClient) -> None:
    resolucion = await resolver_socio(api_client, "María López")
    assert resolucion.estado == "resuelto"
    assert resolucion.resuelto is not None
    assert resolucion.resuelto.id == 3
    assert resolucion.resuelto.saldo == 250000


async def test_resolver_socio_homonimos_pedro_gomez(api_client: ApiClient) -> None:
    resolucion = await resolver_socio(api_client, "pedro")
    assert resolucion.estado == "ambiguo"
    ids = {c.id for c in resolucion.candidatos}
    assert ids == {1, 2}


# ── resolver_letra contra el mock real ───────────────────────────────────────


async def test_resolver_letra_sin_creditos(api_client: ApiClient) -> None:
    resolucion = await resolver_letra(api_client, socio_id=3, letra_hint=None)
    assert resolucion.estado == "no_encontrado"


async def test_resolver_letra_un_credito_sin_hint(api_client: ApiClient) -> None:
    resolucion = await resolver_letra(api_client, socio_id=1, letra_hint=None)
    assert resolucion.estado == "resuelto"
    assert resolucion.letra_id == 450


async def test_resolver_letra_con_hint_confia_en_el_operador(api_client: ApiClient) -> None:
    resolucion = await resolver_letra(api_client, socio_id=1, letra_hint="450")
    assert resolucion.estado == "resuelto"
    assert resolucion.letra_id == 450


async def test_resolver_letra_con_hint_no_numerico_cae_a_lookup(api_client: ApiClient) -> None:
    resolucion = await resolver_letra(api_client, socio_id=1, letra_hint="la de siempre")
    assert resolucion.estado == "resuelto"
    assert resolucion.letra_id == 450


# ── resolver_letra ambiguo (el mock no tiene socios con 2+ créditos) ─────────


async def test_resolver_letra_multiples_creditos() -> None:
    cliente = AsyncMock()
    cliente.get_creditos_socio.return_value = CreditosResponse(
        creditos=[
            CreditoResumen(
                letra_id=450,
                capital_original=2_000_000,
                interes_tasa=0.02,
                n_cuotas_total=24,
                fecha_inicio="2025-03-01",
                socios=["Pedro Antonio Gómez Ruiz"],
            ),
            CreditoResumen(
                letra_id=451,
                capital_original=1_000_000,
                interes_tasa=0.02,
                n_cuotas_total=12,
                fecha_inicio="2025-06-01",
                socios=["Pedro Antonio Gómez Ruiz"],
            ),
        ]
    )
    resolucion = await resolver_letra(cliente, socio_id=1, letra_hint=None)
    assert resolucion.estado == "ambiguo"
    assert {c.letra_id for c in resolucion.candidatos} == {450, 451}


# ── formateo y parseo de selección ────────────────────────────────────────────


def test_formatear_lista_socios() -> None:
    candidatos = [
        SocioSearchItem(
            id=1,
            nombres="Pedro Antonio",
            apellidos="Gómez Ruiz",
            nombre_completo="Pedro Antonio Gómez Ruiz",
            score=0.95,
        ),
        SocioSearchItem(
            id=2,
            nombres="Pedro Luis",
            apellidos="Gómez Castro",
            nombre_completo="Pedro Luis Gómez Castro",
            score=0.90,
        ),
    ]
    texto = formatear_lista_socios(candidatos)
    assert "1. Pedro Antonio Gómez Ruiz" in texto
    assert "2. Pedro Luis Gómez Castro" in texto


def test_formatear_lista_letras() -> None:
    candidatos = [
        CreditoResumen(
            letra_id=450,
            capital_original=2_000_000,
            interes_tasa=0.02,
            n_cuotas_total=24,
            fecha_inicio="2025-03-01",
            socios=["Pedro"],
        ),
    ]
    texto = formatear_lista_letras(candidatos)
    assert "1. Letra 450" in texto


def test_parsear_seleccion_valida() -> None:
    assert parsear_seleccion("1", 3) == 0
    assert parsear_seleccion("3", 3) == 2


def test_parsear_seleccion_acepta_puntuacion_y_espacios() -> None:
    assert parsear_seleccion("1.", 3) == 0
    assert parsear_seleccion("2)", 3) == 1
    assert parsear_seleccion(" 3 ", 3) == 2
    assert parsear_seleccion("(1)", 3) == 0
    assert parsear_seleccion("el 2", 3) == 1


def test_parsear_seleccion_acepta_ordinales_en_espanol() -> None:
    assert parsear_seleccion("uno", 3) == 0
    assert parsear_seleccion("primero", 3) == 0
    assert parsear_seleccion("el primero", 3) == 0
    assert parsear_seleccion("segundo", 3) == 1
    assert parsear_seleccion("la segunda", 3) == 1
    assert parsear_seleccion("tercero", 3) == 2


def test_parsear_seleccion_invalida() -> None:
    assert parsear_seleccion("0", 3) is None
    assert parsear_seleccion("4", 3) is None
    assert parsear_seleccion("no sé", 3) is None
    assert parsear_seleccion("", 3) is None
    assert parsear_seleccion("undecimo", 3) is None
    assert parsear_seleccion("Jose David Ruano", 3) is None

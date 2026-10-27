import json

from coop_bot.api.cliente import ApiClient
from coop_bot.notificaciones.entregas import consultar_entregas, texto_entregas, traducir_error_meta
from coop_contracts import mock_server
from coop_contracts.respuestas import EntregaPorAvisar


def _entrega(resultado: str, **extra: object) -> EntregaPorAvisar:
    datos: dict[str, object] = {
        "id": 1,
        "socio_nombre": "Pedro Gómez",
        "resultado": resultado,
        "documento_tipo": "recordatorio_cuota",
        "detalle": json.dumps({"numero_cuota": "3", "numero_letra": "12"}),
    }
    datos.update(extra)
    return EntregaPorAvisar(**datos)  # type: ignore[arg-type]


# ── traducción de errores ────────────────────────────────────────────────────


def test_traduce_el_error_de_pago() -> None:
    texto = traducir_error_meta("131042: Business eligibility payment issue")
    assert "pago" in texto and "131042" in texto


def test_error_desconocido_conserva_el_texto_de_meta() -> None:
    assert traducir_error_meta("999999: Algo raro") == "999999: Algo raro"


def test_error_vacio() -> None:
    assert "no dio detalle" in traducir_error_meta(None)


# ── redacción del aviso ──────────────────────────────────────────────────────


def test_texto_vacio_si_no_hay_entregas() -> None:
    assert texto_entregas([]) == ""


def test_llego_nombra_recordatorio_con_cuota_y_credito() -> None:
    texto = texto_entregas([_entrega("delivered")])
    assert "Ya les llegó" in texto
    assert "Pedro Gómez" in texto
    assert "recordatorio de la cuota #3 del crédito #12" in texto


def test_llego_un_comprobante() -> None:
    texto = texto_entregas([_entrega("delivered", documento_tipo="recibo", detalle=None)])
    assert "su comprobante" in texto and "recordatorio" not in texto


def test_fallo_explica_el_motivo_de_pago() -> None:
    texto = texto_entregas([_entrega("failed", error="131042: Business eligibility payment issue")])
    assert "NO les llegó" in texto
    assert "Pedro Gómez" in texto
    assert "método de pago" in texto


def test_sin_confirmacion_lo_dice_con_claridad() -> None:
    texto = texto_entregas([_entrega("sin_confirmacion")])
    assert "no confirmó la entrega" in texto and "Pedro Gómez" in texto


def test_detalle_ilegible_no_rompe_el_aviso() -> None:
    texto = texto_entregas([_entrega("delivered", detalle="no es json")])
    assert "recordatorio de cuota" in texto


def test_separa_llegaron_de_fallaron_en_un_mismo_aviso() -> None:
    texto = texto_entregas(
        [
            _entrega("delivered", id=1, socio_nombre="Ana"),
            _entrega("failed", id=2, socio_nombre="Luis", error="131026: x"),
        ]
    )
    assert texto.index("Ana") < texto.index("Luis")
    assert "Ya les llegó" in texto and "NO les llegó" in texto


# ── contra la API ────────────────────────────────────────────────────────────


async def test_consulta_y_marca_avisadas_contra_la_api(api_client: ApiClient) -> None:
    assert await consultar_entregas(api_client) == ("", [], [])

    mock_server._state["notificaciones"][0].update({"entrega_estado": "delivered"})
    texto, ids, nombres = await consultar_entregas(api_client)
    assert "María López Herrera" in texto and ids == [1]
    assert nombres == ["María López Herrera"]

    await api_client.marcar_entregas_avisadas(ids)
    assert await consultar_entregas(api_client) == ("", [], [])

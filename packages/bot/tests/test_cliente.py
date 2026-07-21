import uuid

import httpx
import pytest
from coop_bot.api.cliente import ApiClient, ApiError
from coop_contracts.respuestas import (
    AporteReqItem,
    AportesRequest,
    PagoReqItem,
    PagosRequest,
    RetirosRequest,
)


def _idem() -> str:
    return str(uuid.uuid4())


# ── Consultas ────────────────────────────────────────────────────────────────


async def test_buscar_socios_devuelve_resultados(api_client: ApiClient) -> None:
    resp = await api_client.buscar_socios("pedro")
    ids = {s.id for s in resp.socios}
    assert ids == {1, 2}


async def test_get_socio_existente(api_client: ApiClient) -> None:
    socio = await api_client.get_socio(1)
    assert socio.id == 1
    assert socio.saldo == 320000


async def test_get_socio_inexistente_lanza_api_error(api_client: ApiClient) -> None:
    with pytest.raises(ApiError) as exc_info:
        await api_client.get_socio(999)
    assert exc_info.value.codigo == "SOCIO_NO_ENCONTRADO"
    assert exc_info.value.status_code == 404


async def test_get_caja(api_client: ApiClient) -> None:
    caja = await api_client.get_caja()
    assert caja.saldo_en_caja == 5830000


# ── Autenticación / idempotencia (shape de error no uniforme) ───────────────


async def test_sin_token_lanza_api_error_401(mock_transport) -> None:
    client = ApiClient(base_url="http://mock", token="token-incorrecto", transport=mock_transport)
    try:
        with pytest.raises(ApiError) as exc_info:
            await client.buscar_socios("pedro")
        assert exc_info.value.status_code == 401
        assert exc_info.value.codigo == "NO_AUTORIZADO"
        assert "Traceback" not in exc_info.value.mensaje
    finally:
        await client.aclose()


async def test_post_sin_idempotency_key_lanza_400(api_client: ApiClient) -> None:
    # _post siempre manda el header; forzamos un envío directo sin él para
    # cubrir el mismo shape de error de string plano que devuelve el mock.
    response = await api_client._client.post(
        "/operaciones/retiros", json={"socio_id": 1, "monto": 1000}
    )
    assert response.status_code == 400


# ── Operaciones ──────────────────────────────────────────────────────────────


async def test_registrar_aportes(api_client: ApiClient) -> None:
    body = AportesRequest(recibi_de_id=1, aportes=[AporteReqItem(socio_id=1, monto=80000)])
    resp = await api_client.registrar_aportes(body, _idem())
    assert resp.recibo_id
    assert resp.aportes[0].saldo_nuevo == 400000


async def test_registrar_retiro_saldo_insuficiente(api_client: ApiClient) -> None:
    body = RetirosRequest(socio_id=1, monto=999_999_999)
    with pytest.raises(ApiError) as exc_info:
        await api_client.registrar_retiro(body, _idem())
    assert exc_info.value.codigo == "SALDO_INSUFICIENTE"
    assert exc_info.value.status_code == 422


async def test_registrar_pagos(api_client: ApiClient) -> None:
    body = PagosRequest(
        recibi_de_id=1,
        pagos=[PagoReqItem(socio_id=1, letra_id=450, n_cuotas=1, abono_capital=0)],
    )
    resp = await api_client.registrar_pagos(body, _idem())
    assert resp.pagos[0].letra_id == 450


async def test_idempotency_key_repetida_mismo_payload_devuelve_resultado_original(
    api_client: ApiClient,
) -> None:
    key = _idem()
    body = RetirosRequest(socio_id=1, monto=1000)
    primero = await api_client.registrar_retiro(body, key)
    segundo = await api_client.registrar_retiro(body, key)
    assert primero.recibo_id == segundo.recibo_id


async def test_idempotency_key_repetida_payload_distinto_lanza_409(
    api_client: ApiClient,
) -> None:
    key = _idem()
    await api_client.registrar_retiro(RetirosRequest(socio_id=1, monto=1000), key)
    with pytest.raises(ApiError) as exc_info:
        await api_client.registrar_retiro(RetirosRequest(socio_id=1, monto=2000), key)
    assert exc_info.value.status_code == 409
    assert exc_info.value.codigo == "IDEMPOTENCY_CONFLICT"


# ── Notificaciones ───────────────────────────────────────────────────────────


async def test_get_notificaciones_pendientes_devuelve_la_semilla_del_mock(
    api_client: ApiClient,
) -> None:
    resp = await api_client.get_notificaciones_pendientes()
    assert len(resp.notificaciones) == 1
    assert resp.notificaciones[0].socio_id == 3


async def test_patch_notificacion_marca_como_enviada(api_client: ApiClient) -> None:
    await api_client.patch_notificacion(1, "enviada")
    resp = await api_client.get_notificaciones_pendientes()
    assert resp.notificaciones == []


async def test_patch_notificacion_inexistente_lanza_404(api_client: ApiClient) -> None:
    with pytest.raises(ApiError) as exc_info:
        await api_client.patch_notificacion(999, "enviada")
    assert exc_info.value.status_code == 404


# ── Manejo de errores extendido (401/404/422/500) ────────────────────────────


async def test_error_de_negocio_incluye_codigo_y_mensaje_en_espanol(
    api_client: ApiClient,
) -> None:
    with pytest.raises(ApiError) as exc_info:
        await api_client.get_socio(999)
    assert exc_info.value.codigo == "SOCIO_NO_ENCONTRADO"
    assert "Traceback" not in exc_info.value.mensaje
    assert exc_info.value.mensaje == "No existe un socio con ID 999."


async def test_error_500_se_muestra_en_espanol_sin_stacktrace() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = ApiClient(
        base_url="http://mock", token="mock-secret", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(ApiError) as exc_info:
            await client.get_caja()
        assert exc_info.value.status_code == 500
        assert exc_info.value.codigo == "ERROR_INTERNO"
        assert "Traceback" not in exc_info.value.mensaje
        assert "intenta de nuevo" in exc_info.value.mensaje.lower()
    finally:
        await client.aclose()

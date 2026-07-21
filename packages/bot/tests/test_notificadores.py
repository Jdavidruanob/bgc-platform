import json

import httpx
from coop_bot.config import Config
from coop_bot.notificaciones.notificadores import (
    CloudApiNotificador,
    NotificadorConFallback,
    WaMeLinkNotificador,
    construir_notificador,
)
from coop_contracts.notificador import ResultadoEnvio


def _config(**overrides: object) -> Config:
    base: dict[str, object] = {
        "coop_api_base_url": "http://localhost:8001",
        "coop_api_token": "mock-secret",
        "telegram_bot_token": "123:abc",
        "telegram_operador_chat_id": 999,
        "openai_api_key": "sk-test",
    }
    base.update(overrides)
    return Config(**base)  # type: ignore[arg-type]


# ── CloudApiNotificador ────────────────────────────────────────────────────


def test_cloud_api_notificador_envio_exitoso() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer meta-token"
        assert request.url.path == "/v20.0/1234567890/messages"
        payload = json.loads(request.read())
        assert payload["to"] == "573112223344"
        assert payload["text"]["body"] == "hola"
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    notificador = CloudApiNotificador(
        token="meta-token",
        phone_number_id="1234567890",
        transport=httpx.MockTransport(handler),
    )
    resultado = notificador.enviar("+573112223344", "hola")

    assert resultado.exitoso is True
    assert resultado.canal == "cloud_api"


def test_cloud_api_notificador_rechazado_por_meta_no_es_exitoso() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Recipient not on WhatsApp"}})

    notificador = CloudApiNotificador(token="t", phone_number_id="1", transport=httpx.MockTransport(handler))
    resultado = notificador.enviar("+573112223344", "hola")

    assert resultado.exitoso is False
    assert resultado.canal == "cloud_api"
    assert resultado.error is not None
    assert "Recipient not on WhatsApp" in resultado.error


def test_cloud_api_notificador_error_de_red_no_es_exitoso() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    notificador = CloudApiNotificador(token="t", phone_number_id="1", transport=httpx.MockTransport(handler))
    resultado = notificador.enviar("+573112223344", "hola")

    assert resultado.exitoso is False
    assert resultado.canal == "cloud_api"


# ── WaMeLinkNotificador ──────────────────────────────────────────────────────


def test_wa_me_link_notificador_genera_url_con_texto_precargado() -> None:
    notificador = WaMeLinkNotificador()
    resultado = notificador.enviar("+573112223344", "hola mundo")

    assert resultado.exitoso is True
    assert resultado.canal == "wa_me_link"
    assert resultado.wa_me_url is not None
    assert resultado.wa_me_url.startswith("https://wa.me/573112223344?text=")
    assert "hola" in resultado.wa_me_url


def test_wa_me_link_notificador_numero_vacio_no_es_exitoso() -> None:
    resultado = WaMeLinkNotificador().enviar("", "hola")
    assert resultado.exitoso is False


# ── NotificadorConFallback ───────────────────────────────────────────────────


class _NotificadorFijo:
    def __init__(self, resultado: ResultadoEnvio) -> None:
        self._resultado = resultado

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        return self._resultado


def test_fallback_no_se_usa_si_el_primario_funciona() -> None:
    primario = _NotificadorFijo(ResultadoEnvio(exitoso=True, canal="cloud_api"))
    compuesto = NotificadorConFallback(primario, WaMeLinkNotificador())

    resultado = compuesto.enviar("+573112223344", "hola")

    assert resultado.canal == "cloud_api"


def test_fallback_se_usa_si_el_primario_falla() -> None:
    primario = _NotificadorFijo(ResultadoEnvio(exitoso=False, canal="cloud_api", error="rechazado"))
    compuesto = NotificadorConFallback(primario, WaMeLinkNotificador())

    resultado = compuesto.enviar("+573112223344", "hola")

    assert resultado.exitoso is True
    assert resultado.canal == "wa_me_link"


# ── construir_notificador ─────────────────────────────────────────────────────


def test_construir_notificador_sin_credenciales_meta_usa_solo_wa_me() -> None:
    notificador = construir_notificador(_config())
    assert isinstance(notificador, WaMeLinkNotificador)


def test_construir_notificador_con_credenciales_meta_usa_fallback_compuesto() -> None:
    notificador = construir_notificador(_config(whatsapp_cloud_api_token="t", whatsapp_phone_number_id="1"))
    assert isinstance(notificador, NotificadorConFallback)

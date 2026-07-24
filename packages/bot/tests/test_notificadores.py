import json

import httpx
from coop_bot.config import Config
from coop_bot.notificaciones.notificadores import (
    CloudApiNotificador,
    NotificadorConFallback,
    WaMeLinkNotificador,
    construir_notificador,
)
from coop_contracts.notificador import ParamsPlantilla, ResultadoEnvio


def _config(**overrides: object) -> Config:
    base: dict[str, object] = {
        "coop_api_base_url": "http://localhost:8001",
        "coop_api_token": "mock-secret",
        "telegram_bot_token": "123:abc",
        "telegram_operador_chat_ids": (999,),
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


def test_cloud_api_notificador_enviar_documento_sube_y_manda_mensaje() -> None:
    llamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request.url.path)
        if request.url.path.endswith("/media"):
            assert b'filename="Recibo_1.pdf"' in request.content
            return httpx.Response(200, json={"id": "media-123"})
        payload = json.loads(request.read())
        assert payload["type"] == "document"
        assert payload["document"]["id"] == "media-123"
        assert payload["document"]["filename"] == "Recibo_1.pdf"
        assert payload["document"]["caption"] == "Tu recibo"
        return httpx.Response(200, json={"messages": [{"id": "wamid.2"}]})

    notificador = CloudApiNotificador(
        token="meta-token", phone_number_id="1234567890", transport=httpx.MockTransport(handler)
    )
    resultado = notificador.enviar_documento(
        "+573112223344", "Tu recibo", b"%PDF-1.4 contenido", "Recibo_1.pdf"
    )

    assert resultado.exitoso is True
    assert resultado.canal == "cloud_api"
    assert llamadas == ["/v20.0/1234567890/media", "/v20.0/1234567890/messages"]


def test_cloud_api_notificador_enviar_documento_falla_si_falla_la_subida() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Unsupported media type"}})

    notificador = CloudApiNotificador(token="t", phone_number_id="1", transport=httpx.MockTransport(handler))
    resultado = notificador.enviar_documento("+573112223344", "texto", b"contenido", "a.pdf")

    assert resultado.exitoso is False
    assert resultado.error is not None
    assert "Unsupported media type" in resultado.error


def test_cloud_api_notificador_usa_plantilla_con_el_pdf_en_el_encabezado() -> None:
    """Con plantilla configurada se manda `type: template`: es lo único que Meta
    permite para escribirle a un socio fuera de la ventana de 24h."""
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-999"})
        payloads.append(json.loads(request.read()))
        return httpx.Response(200, json={"messages": [{"id": "wamid.3"}]})

    notificador = CloudApiNotificador(
        token="t",
        phone_number_id="1",
        plantilla="comprobante_operacion",
        plantilla_idioma="es",
        transport=httpx.MockTransport(handler),
    )
    resultado = notificador.enviar_documento(
        "+573112223344",
        "texto largo que no se usa en plantilla",
        b"%PDF-1.4",
        "Recibo_7.pdf",
        ParamsPlantilla(nombre="Pedro", detalle="Registramos tu aporte de $50.000"),
    )

    assert resultado.exitoso is True
    payload = payloads[0]
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "comprobante_operacion"
    assert payload["template"]["language"]["code"] == "es"

    encabezado, cuerpo = payload["template"]["components"]
    assert encabezado["parameters"][0]["document"] == {
        "id": "media-999",
        "filename": "Recibo_7.pdf",
    }
    assert [p["text"] for p in cuerpo["parameters"]] == [
        "Pedro",
        "Registramos tu aporte de $50.000",
    ]


def test_cloud_api_notificador_sin_plantilla_configurada_manda_documento_libre() -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-1"})
        payloads.append(json.loads(request.read()))
        return httpx.Response(200, json={"messages": [{"id": "wamid.4"}]})

    notificador = CloudApiNotificador(token="t", phone_number_id="1", transport=httpx.MockTransport(handler))
    notificador.enviar_documento(
        "+573112223344",
        "Tu recibo",
        b"%PDF",
        "a.pdf",
        ParamsPlantilla(nombre="Pedro", detalle="algo"),
    )

    assert payloads[0]["type"] == "document"


def test_params_plantilla_se_aplanan_a_una_linea() -> None:
    """Meta rechaza variables con saltos de línea o espacios repetidos."""
    limpios = ParamsPlantilla(nombre="Pedro", detalle="linea uno\nlinea    dos\ttres").limpiar()

    assert limpios.detalle == "linea uno linea dos tres"


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


def test_wa_me_link_notificador_enviar_documento_degrada_a_texto() -> None:
    """wa.me no puede adjuntar archivos: manda un link de texto avisando del
    documento, en vez de fallar."""
    resultado = WaMeLinkNotificador().enviar_documento(
        "+573112223344", "Tu recibo", b"contenido", "Recibo_1.pdf"
    )

    assert resultado.exitoso is True
    assert resultado.canal == "wa_me_link"
    assert resultado.wa_me_url is not None
    assert "Recibo_1.pdf" in resultado.wa_me_url


# ── NotificadorConFallback ───────────────────────────────────────────────────


class _NotificadorFijo:
    def __init__(self, resultado: ResultadoEnvio) -> None:
        self._resultado = resultado

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        return self._resultado

    def enviar_documento(
        self,
        numero_e164: str,
        texto: str,
        contenido: bytes,
        nombre_archivo: str,
        plantilla: ParamsPlantilla | None = None,
    ) -> ResultadoEnvio:
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


def test_fallback_enviar_documento_usa_fallback_si_primario_falla() -> None:
    primario = _NotificadorFijo(ResultadoEnvio(exitoso=False, canal="cloud_api", error="rechazado"))
    compuesto = NotificadorConFallback(primario, WaMeLinkNotificador())

    resultado = compuesto.enviar_documento("+573112223344", "Tu recibo", b"contenido", "Recibo_1.pdf")

    assert resultado.exitoso is True
    assert resultado.canal == "wa_me_link"
    assert resultado.wa_me_url is not None
    assert "Recibo_1.pdf" in resultado.wa_me_url


# ── construir_notificador ─────────────────────────────────────────────────────


def test_construir_notificador_sin_credenciales_meta_usa_solo_wa_me() -> None:
    notificador = construir_notificador(_config())
    assert isinstance(notificador, WaMeLinkNotificador)


def test_construir_notificador_con_credenciales_meta_usa_fallback_compuesto() -> None:
    notificador = construir_notificador(_config(whatsapp_cloud_api_token="t", whatsapp_phone_number_id="1"))
    assert isinstance(notificador, NotificadorConFallback)

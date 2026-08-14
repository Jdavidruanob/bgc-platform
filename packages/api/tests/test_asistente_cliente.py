"""Tests unitarios del cliente de WhatsApp Cloud API del asistente (payloads
exactos hacia Meta) y del parser del sobre entrante — sin pasar por el
webhook HTTP."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from coop_api.asistente.entrada import parsear_mensajes
from coop_api.asistente.whatsapp_cliente import Boton, ClienteCloudApi, Documento, Fila


def _cliente(handler: Callable[[httpx.Request], httpx.Response]) -> ClienteCloudApi:
    return ClienteCloudApi("token-x", "pnid123", transport=httpx.MockTransport(handler))


# ── ClienteCloudApi: payloads ────────────────────────────────────────────────


def test_enviar_texto_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token-x"
        assert request.url.path == "/v20.0/pnid123/messages"
        payload = json.loads(request.read())
        assert payload["to"] == "573001234567"
        assert payload["type"] == "text"
        assert payload["text"]["body"] == "hola"
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    assert _cliente(handler).enviar_texto("+573001234567", "hola") is True


def test_enviar_botones_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["type"] == "interactive"
        interactive = payload["interactive"]
        assert interactive["type"] == "button"
        assert interactive["body"]["text"] == "¿Qué deseas?"
        botones = interactive["action"]["buttons"]
        assert [b["reply"]["id"] for b in botones] == ["menu:aportes", "menu:creditos"]
        assert [b["reply"]["title"] for b in botones] == ["Mi saldo de aportes", "Mis créditos"]
        assert all(b["type"] == "reply" for b in botones)
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    cliente = _cliente(handler)
    botones = [Boton("menu:aportes", "Mi saldo de aportes"), Boton("menu:creditos", "Mis créditos")]
    assert cliente.enviar_botones("+573001234567", "¿Qué deseas?", botones) is True


def test_enviar_botones_recorta_titulo_largo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        titulo = payload["interactive"]["action"]["buttons"][0]["reply"]["title"]
        assert len(titulo) <= 20
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    cliente = _cliente(handler)
    boton = Boton("x", "Un título de botón absurdamente largo que no cabe")
    assert cliente.enviar_botones("+57300", "cuerpo", [boton]) is True


def test_enviar_lista_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        interactive = payload["interactive"]
        assert interactive["type"] == "list"
        filas = interactive["action"]["sections"][0]["rows"]
        assert [f["id"] for f in filas] == ["liq:letra:1", "liq:todos"]
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    cliente = _cliente(handler)
    filas = [Fila("liq:letra:1", "Letra #1"), Fila("liq:todos", "De todos")]
    assert cliente.enviar_lista("+57300", "elige", "Ver créditos", filas) is True


def test_enviar_documento_sube_media_y_manda_mensaje() -> None:
    llamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request.url.path)
        if request.url.path.endswith("/media"):
            assert b"filename=" in request.read() or request.headers.get("content-type", "").startswith(
                "multipart/form-data"
            )
            return httpx.Response(200, json={"id": "media-abc"})
        payload = json.loads(request.read())
        assert payload["type"] == "document"
        assert payload["document"]["id"] == "media-abc"
        assert payload["document"]["filename"] == "Liquidacion_letra_1.pdf"
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    cliente = _cliente(handler)
    documento = Documento(b"%PDF-1.4", "Liquidacion_letra_1.pdf", "application/pdf", "aquí tienes")
    assert cliente.enviar_documento("+57300", documento) is True
    assert llamadas == ["/v20.0/pnid123/media", "/v20.0/pnid123/messages"]


def test_enviar_documento_falla_si_meta_no_da_media_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    cliente = _cliente(handler)
    documento = Documento(b"%PDF-1.4", "x.pdf", "application/pdf", "cap")
    assert cliente.enviar_documento("+57300", documento) is False


def test_enviar_texto_error_de_red() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    assert _cliente(handler).enviar_texto("+57300", "hola") is False


# ── parsear_mensajes ─────────────────────────────────────────────────────────


def _sobre(mensaje: dict) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {"messages": [mensaje]},
                    }
                ]
            }
        ]
    }


def test_parsear_list_reply() -> None:
    mensaje = {
        "from": "573001234567",
        "id": "wamid.1",
        "timestamp": "1",
        "type": "interactive",
        "interactive": {"type": "list_reply", "list_reply": {"id": "liq:letra:1", "title": "Letra #1"}},
    }
    resultado = parsear_mensajes(_sobre(mensaje))
    assert len(resultado) == 1
    assert resultado[0].tipo == "boton"
    assert resultado[0].boton_id == "liq:letra:1"


def test_parsear_quick_reply_de_plantilla() -> None:
    mensaje = {
        "from": "573001234567",
        "id": "wamid.1",
        "timestamp": "1",
        "type": "button",
        "button": {"payload": "menu:aportes", "text": "Mi saldo de aportes"},
    }
    resultado = parsear_mensajes(_sobre(mensaje))
    assert resultado[0].tipo == "boton"
    assert resultado[0].boton_id == "menu:aportes"


def test_parsear_reaccion_es_otro() -> None:
    mensaje = {
        "from": "573001234567",
        "id": "wamid.1",
        "timestamp": "1",
        "type": "reaction",
        "reaction": {"message_id": "wamid.0", "emoji": "👍"},
    }
    resultado = parsear_mensajes(_sobre(mensaje))
    assert resultado[0].tipo == "otro"


def test_parsear_statuses_no_produce_mensajes() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {"statuses": [{"id": "wamid.s1", "status": "delivered"}]},
                    }
                ]
            }
        ]
    }
    assert parsear_mensajes(payload) == []


def test_parsear_payload_malformado_no_revienta() -> None:
    assert parsear_mensajes({}) == []
    assert parsear_mensajes({"entry": "no-es-lista"}) == []
    assert parsear_mensajes({"entry": [{"changes": "no-es-lista"}]}) == []
    assert parsear_mensajes(None) == []
    assert parsear_mensajes("texto plano") == []


def test_parsear_mensaje_sin_from_se_descarta() -> None:
    assert parsear_mensajes(_sobre({"id": "wamid.1", "type": "text", "text": {"body": "hola"}})) == []

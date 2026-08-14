"""Cliente saliente de Meta WhatsApp Cloud API para el asistente de socios.

Es un cliente distinto del `CloudApiNotificador` del bot
(`coop_bot.notificaciones.notificadores`) a propósito: ese modela avisos
"dispara y olvida" con plantilla y fallback a wa.me; este necesita mensajes
interactivos (botones, listas) y nunca tiene fallback — si Meta falla, el
socio simplemente vuelve a escribir. `coop-bot` tampoco es una dependencia de
`coop-api` (ni su código se copia a la imagen Docker de la API), así que
importarlo no es una opción. La duplicación de la subida de media es
aceptable; si crece, se puede extraer a `coop_contracts`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Protocol

import httpx
from fastapi import Depends

from coop_api.asistente.config import desde_entorno

logger = logging.getLogger(__name__)

# Límites de Meta para mensajes interactivos (Cloud API), ver
# developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-*.
_LIMITE_CUERPO_INTERACTIVO = 1024
_LIMITE_PIE = 60
_LIMITE_TITULO_BOTON = 20
_LIMITE_TITULO_FILA = 24
_LIMITE_DESCRIPCION_FILA = 72
_LIMITE_TEXTO_LIBRE = 4096
_MAX_BOTONES = 3
_MAX_FILAS_LISTA = 10

PIE_ASISTENTE = "Consulta de solo lectura · BGC"


def _recortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    return texto[: limite - 1].rstrip() + "…"


@dataclass(frozen=True)
class Boton:
    id: str
    titulo: str


@dataclass(frozen=True)
class Fila:
    id: str
    titulo: str
    descripcion: str = ""


@dataclass(frozen=True)
class Documento:
    contenido: bytes
    nombre_archivo: str
    mime: str
    caption: str = ""


class ClienteWhatsApp(Protocol):
    def enviar_texto(self, numero_e164: str, texto: str) -> bool: ...

    def enviar_botones(self, numero_e164: str, texto: str, botones: list[Boton]) -> bool: ...

    def enviar_lista(self, numero_e164: str, texto: str, texto_boton: str, filas: list[Fila]) -> bool: ...

    def enviar_documento(self, numero_e164: str, documento: Documento) -> bool: ...


class ClienteCloudApi:
    """Implementación real, sobre Meta WhatsApp Cloud API."""

    _BASE_URL = "https://graph.facebook.com"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        *,
        version: str = "v20.0",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._version = version
        self._client = httpx.Client(
            base_url=self._BASE_URL,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _post_mensaje(self, payload: dict[str, Any]) -> bool:
        try:
            respuesta = self._client.post(f"/{self._version}/{self._phone_number_id}/messages", json=payload)
        except httpx.HTTPError as exc:
            logger.error("Fallo de red enviando mensaje de WhatsApp: %s", exc)
            return False
        if respuesta.is_error:
            logger.error("Meta rechazó el mensaje de WhatsApp: %s", _extraer_error_meta(respuesta))
            return False
        return True

    def enviar_texto(self, numero_e164: str, texto: str) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero_e164.removeprefix("+"),
            "type": "text",
            "text": {"body": _recortar(texto, _LIMITE_TEXTO_LIBRE)},
        }
        return self._post_mensaje(payload)

    def enviar_botones(self, numero_e164: str, texto: str, botones: list[Boton]) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero_e164.removeprefix("+"),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": _recortar(texto, _LIMITE_CUERPO_INTERACTIVO)},
                "footer": {"text": _recortar(PIE_ASISTENTE, _LIMITE_PIE)},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": b.id,
                                "title": _recortar(b.titulo, _LIMITE_TITULO_BOTON),
                            },
                        }
                        for b in botones[:_MAX_BOTONES]
                    ]
                },
            },
        }
        return self._post_mensaje(payload)

    def enviar_lista(self, numero_e164: str, texto: str, texto_boton: str, filas: list[Fila]) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero_e164.removeprefix("+"),
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": _recortar(texto, _LIMITE_CUERPO_INTERACTIVO)},
                "footer": {"text": _recortar(PIE_ASISTENTE, _LIMITE_PIE)},
                "action": {
                    "button": _recortar(texto_boton, _LIMITE_TITULO_BOTON),
                    "sections": [
                        {
                            "rows": [
                                {
                                    "id": f.id,
                                    "title": _recortar(f.titulo, _LIMITE_TITULO_FILA),
                                    "description": _recortar(f.descripcion, _LIMITE_DESCRIPCION_FILA),
                                }
                                for f in filas[:_MAX_FILAS_LISTA]
                            ]
                        }
                    ],
                },
            },
        }
        return self._post_mensaje(payload)

    def enviar_documento(self, numero_e164: str, documento: Documento) -> bool:
        try:
            subida = self._client.post(
                f"/{self._version}/{self._phone_number_id}/media",
                data={"messaging_product": "whatsapp", "type": documento.mime},
                files={"file": (documento.nombre_archivo, documento.contenido, documento.mime)},
            )
        except httpx.HTTPError as exc:
            logger.error("Fallo de red subiendo documento a WhatsApp: %s", exc)
            return False
        if subida.is_error:
            logger.error("Meta rechazó la subida del documento: %s", _extraer_error_meta(subida))
            return False

        media_id = subida.json().get("id")
        if not media_id:
            logger.error("Meta no devolvió media id al subir el documento")
            return False

        payload = {
            "messaging_product": "whatsapp",
            "to": numero_e164.removeprefix("+"),
            "type": "document",
            "document": {
                "id": media_id,
                "filename": documento.nombre_archivo,
                "caption": _recortar(documento.caption, _LIMITE_TEXTO_LIBRE),
            },
        }
        return self._post_mensaje(payload)

    def cerrar(self) -> None:
        self._client.close()


class ClienteInactivo:
    """Se usa cuando faltan credenciales de Meta: registra en el log y no
    envía nada. Evita que el asistente reviente en un entorno sin configurar
    (ej. staging) — simplemente no le contesta a nadie."""

    def enviar_texto(self, numero_e164: str, texto: str) -> bool:
        logger.warning("Asistente WhatsApp sin credenciales de Meta: no se envió texto a %s", numero_e164)
        return False

    def enviar_botones(self, numero_e164: str, texto: str, botones: list[Boton]) -> bool:
        logger.warning("Asistente WhatsApp sin credenciales: no se enviaron botones a %s", numero_e164)
        return False

    def enviar_lista(self, numero_e164: str, texto: str, texto_boton: str, filas: list[Fila]) -> bool:
        logger.warning("Asistente WhatsApp sin credenciales de Meta: no se envió lista a %s", numero_e164)
        return False

    def enviar_documento(self, numero_e164: str, documento: Documento) -> bool:
        logger.warning("Asistente WhatsApp sin credenciales de Meta: no se envió documento a %s", numero_e164)
        return False


@dataclass
class ClienteFalso:
    """Doble de prueba: graba cada envío en vez de llamar a Meta."""

    textos: list[tuple[str, str]] = field(default_factory=list)
    botones: list[tuple[str, str, list[Boton]]] = field(default_factory=list)
    listas: list[tuple[str, str, str, list[Fila]]] = field(default_factory=list)
    documentos: list[tuple[str, Documento]] = field(default_factory=list)

    def enviar_texto(self, numero_e164: str, texto: str) -> bool:
        self.textos.append((numero_e164, texto))
        return True

    def enviar_botones(self, numero_e164: str, texto: str, botones: list[Boton]) -> bool:
        self.botones.append((numero_e164, texto, botones))
        return True

    def enviar_lista(self, numero_e164: str, texto: str, texto_boton: str, filas: list[Fila]) -> bool:
        self.listas.append((numero_e164, texto, texto_boton, filas))
        return True

    def enviar_documento(self, numero_e164: str, documento: Documento) -> bool:
        self.documentos.append((numero_e164, documento))
        return True


def get_cliente_whatsapp() -> ClienteWhatsApp:
    """Dependencia de FastAPI: construye el cliente real si hay credenciales
    de Meta configuradas en el servicio API, o un `ClienteInactivo` si no.
    Se sobreescribe en tests con `ClienteFalso` vía `dependency_overrides`."""
    cfg = desde_entorno()
    if cfg.token and cfg.phone_number_id:
        return ClienteCloudApi(cfg.token, cfg.phone_number_id, version=cfg.graph_version)
    return ClienteInactivo()


ClienteWaDep = Annotated[ClienteWhatsApp, Depends(get_cliente_whatsapp)]


def _extraer_error_meta(respuesta: httpx.Response) -> str:
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return f"HTTP {respuesta.status_code}"
    error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return str(error["message"])
    return f"HTTP {respuesta.status_code}"

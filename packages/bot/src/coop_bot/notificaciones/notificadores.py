"""Implementaciones de `Notificador` (ver ADR-010 y `coop_contracts.notificador`).

`MockNotificador` ya viene implementado en `coop_contracts.notificador` y se
usa tal cual en tests. Aquí solo viven las dos implementaciones que le
corresponden a Dev B: el canal real (Meta Cloud API) y su fallback (wa.me).

`Notificador.enviar` es síncrono por contrato (así lo define `coop_contracts`),
así que estas implementaciones usan clientes HTTP síncronos. El procesador de
la cola (`notificaciones.procesador`) es quien se encarga de no bloquear el
event loop al llamarlas.
"""

from __future__ import annotations

import urllib.parse

import httpx
from coop_contracts.notificador import (  # type: ignore[import-untyped]
    Notificador,
    ResultadoEnvio,
)

from coop_bot.config import Config


class CloudApiNotificador:
    """Envía mensajes de texto vía Meta WhatsApp Cloud API.

    Nota: los mensajes proactivos fuera de la ventana de servicio al cliente
    de 24h requieren plantillas de utilidad aprobadas por Meta (ver
    ADR-010). Esta implementación envía texto libre; si Meta la rechaza por
    no usar plantilla, `enviar` devuelve `exitoso=False` y el procesador de
    la cola recurre al fallback wa.me.
    """

    _BASE_URL = "https://graph.facebook.com"
    _VERSION = "v20.0"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._client = httpx.Client(
            base_url=self._BASE_URL,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        payload = {
            "messaging_product": "whatsapp",
            "to": numero_e164.removeprefix("+"),
            "type": "text",
            "text": {"body": texto},
        }
        try:
            respuesta = self._client.post(
                f"/{self._VERSION}/{self._phone_number_id}/messages", json=payload
            )
        except httpx.HTTPError as exc:
            return ResultadoEnvio(exitoso=False, canal="cloud_api", error=str(exc))

        if respuesta.is_error:
            return ResultadoEnvio(
                exitoso=False, canal="cloud_api", error=_extraer_error_meta(respuesta)
            )
        return ResultadoEnvio(exitoso=True, canal="cloud_api")

    def cerrar(self) -> None:
        self._client.close()


class WaMeLinkNotificador:
    """Fallback sin cuenta de Meta: genera un enlace wa.me con el texto
    precargado para que el tesorero lo abra y lo envíe manualmente. No
    envía nada por sí mismo: `exitoso=True` significa que el enlace se
    generó correctamente, no que el mensaje ya llegó al socio.
    """

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        numero = numero_e164.removeprefix("+").strip()
        if not numero:
            return ResultadoEnvio(
                exitoso=False, canal="wa_me_link", error="Número de WhatsApp vacío"
            )
        url = f"https://wa.me/{numero}?text={urllib.parse.quote(texto)}"
        return ResultadoEnvio(exitoso=True, canal="wa_me_link", wa_me_url=url)


class NotificadorConFallback:
    """Intenta con el notificador primario; si falla, recurre al fallback.

    Implementa el flujo de ADR-010: "Si falla → WaMeLinkNotificador.enviar(...)
    o registra error".
    """

    def __init__(self, primario: Notificador, fallback: Notificador) -> None:
        self._primario = primario
        self._fallback = fallback

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        resultado = self._primario.enviar(numero_e164, texto)
        if resultado.exitoso:
            return resultado
        return self._fallback.enviar(numero_e164, texto)


def construir_notificador(config: Config) -> Notificador:
    """Cloud API + fallback wa.me si hay credenciales de Meta; solo wa.me si no."""
    fallback = WaMeLinkNotificador()
    if config.whatsapp_cloud_api_token and config.whatsapp_phone_number_id:
        primario = CloudApiNotificador(
            token=config.whatsapp_cloud_api_token,
            phone_number_id=config.whatsapp_phone_number_id,
        )
        return NotificadorConFallback(primario, fallback)
    return fallback


def _extraer_error_meta(respuesta: httpx.Response) -> str:
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return f"HTTP {respuesta.status_code}"
    error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return str(error["message"])
    return f"HTTP {respuesta.status_code}"

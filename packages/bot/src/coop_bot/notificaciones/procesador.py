"""Procesador de la cola de notificaciones pendientes.

Lee `GET /notificaciones/pendientes`, envía cada una vía `Notificador` y
actualiza su estado con `PATCH /notificaciones/{id}`. Nunca bloquea el flujo
conversacional (ver ADR-010: "las notificaciones nunca son bloqueantes"): se
ejecuta como tarea periódica independiente (ver `main.py`), y el fallo de una
notificación puntual no aborta el procesamiento del resto de la cola.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from coop_contracts.notificador import Notificador
from coop_contracts.respuestas import NotificacionPendiente

from coop_bot.api.cliente import ApiClient, ApiError

logger = logging.getLogger(__name__)


@dataclass
class EnvioRealizado:
    """Un envío que salió bien. `canal` distingue el envío real por WhatsApp
    ('cloud_api') del fallback que solo genera un link ('wa_me_link'): en ese
    segundo caso el socio TODAVÍA no recibió nada, hay que abrir el link."""

    socio_nombre: str
    canal: str
    wa_me_url: str | None = None

    @property
    def entregado(self) -> bool:
        return self.canal != "wa_me_link"


@dataclass
class ResumenProcesamiento:
    enviadas: int = 0
    fallidas: int = 0
    errores: list[str] = field(default_factory=list)
    envios: list[EnvioRealizado] = field(default_factory=list)
    fallos: list[tuple[str, str | None]] = field(default_factory=list)


async def procesar_pendientes(cliente: ApiClient, notificador: Notificador) -> ResumenProcesamiento:
    resumen = ResumenProcesamiento()
    try:
        pendientes = await cliente.get_notificaciones_pendientes()
    except ApiError as exc:
        logger.warning("No se pudo consultar la cola de notificaciones: %s", exc.mensaje)
        resumen.errores.append(exc.mensaje)
        return resumen

    for notificacion in pendientes.notificaciones:
        await _procesar_una(cliente, notificador, notificacion, resumen)

    return resumen


async def _procesar_una(
    cliente: ApiClient,
    notificador: Notificador,
    notificacion: NotificacionPendiente,
    resumen: ResumenProcesamiento,
) -> None:
    documento = await _descargar_documento(cliente, notificacion)

    try:
        if documento is not None:
            contenido, nombre_archivo = documento
            resultado = await asyncio.to_thread(
                notificador.enviar_documento,
                notificacion.numero_e164,
                notificacion.texto,
                contenido,
                nombre_archivo,
            )
        else:
            resultado = await asyncio.to_thread(
                notificador.enviar, notificacion.numero_e164, notificacion.texto
            )
    except Exception as exc:  # noqa: BLE001 - cualquier fallo del canal es recuperable
        logger.exception("El notificador lanzó una excepción para la notificación %s", notificacion.id)
        resumen.fallos.append((notificacion.socio_nombre, str(exc)))
        await _marcar(cliente, notificacion.id, "fallida", str(exc), resumen)
        return

    if resultado.exitoso:
        resumen.envios.append(
            EnvioRealizado(
                socio_nombre=notificacion.socio_nombre,
                canal=resultado.canal,
                wa_me_url=resultado.wa_me_url,
            )
        )
        await _marcar(cliente, notificacion.id, "enviada", None, resumen)
    else:
        resumen.fallos.append((notificacion.socio_nombre, resultado.error))
        await _marcar(cliente, notificacion.id, "fallida", resultado.error, resumen)


async def _descargar_documento(
    cliente: ApiClient, notificacion: NotificacionPendiente
) -> tuple[bytes, str] | None:
    """Trae el PDF a adjuntar, si la notificación tiene uno. None si es de solo
    texto, o si el documento ya no está disponible (se manda solo el texto)."""
    if notificacion.documento_tipo is None or notificacion.documento_id is None:
        return None

    try:
        if notificacion.documento_tipo == "recibo":
            pdf = await cliente.descargar_pdf_recibo(notificacion.documento_id)
            nombre = f"Recibo_{notificacion.documento_id}.pdf"
        elif notificacion.documento_tipo == "liquidacion":
            pdf = await cliente.descargar_pdf_liquidacion(notificacion.documento_id)
            nombre = f"Liquidacion_letra_{notificacion.documento_id}.pdf"
        else:
            return None
    except ApiError:
        logger.warning(
            "No se pudo descargar el documento de la notificación %s", notificacion.id, exc_info=True
        )
        return None

    if pdf is None:
        return None
    return pdf, nombre


async def _marcar(
    cliente: ApiClient,
    notificacion_id: int,
    estado: str,
    error: str | None,
    resumen: ResumenProcesamiento,
) -> None:
    try:
        await cliente.patch_notificacion(notificacion_id, estado, error)
    except ApiError as exc:
        logger.warning(
            "No se pudo actualizar el estado de la notificación %s: %s",
            notificacion_id,
            exc.mensaje,
        )
        resumen.errores.append(exc.mensaje)
        return

    if estado == "enviada":
        resumen.enviadas += 1
    else:
        resumen.fallidas += 1
        if error:
            resumen.errores.append(error)

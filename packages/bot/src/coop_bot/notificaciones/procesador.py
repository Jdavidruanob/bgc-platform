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
class ResumenProcesamiento:
    enviadas: int = 0
    fallidas: int = 0
    errores: list[str] = field(default_factory=list)


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
    try:
        resultado = await asyncio.to_thread(notificador.enviar, notificacion.numero_e164, notificacion.texto)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo del canal es recuperable
        logger.exception("El notificador lanzó una excepción para la notificación %s", notificacion.id)
        await _marcar(cliente, notificacion.id, "fallida", str(exc), resumen)
        return

    if resultado.exitoso:
        await _marcar(cliente, notificacion.id, "enviada", None, resumen)
    else:
        await _marcar(cliente, notificacion.id, "fallida", resultado.error, resumen)


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

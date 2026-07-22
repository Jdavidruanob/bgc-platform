"""Adaptador de Telegram: capa delgada sobre python-telegram-bot.

Descarga audio, llama a Whisper/NLU, y delega toda la lógica de negocio a
`MaquinaEstados`. No conoce las reglas de la cooperativa ni los schemas de
`coop_contracts` más allá de lo que `dialogo.estados` expone.
"""

# mypy: disable-error-code="type-arg"
from __future__ import annotations

import io
import logging
from typing import cast

from coop_contracts.notificador import Notificador
from telegram import InputFile, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from coop_bot.api.cliente import ApiClient
from coop_bot.config import Config
from coop_bot.dialogo.estados import (
    TIMEOUT_SEGUNDOS,
    EstadoDialogo,
    MaquinaEstados,
    RespuestaDialogo,
    SesionDialogo,
)
from coop_bot.nlu.llm_client import LlmClient
from coop_bot.nlu.whisper_client import WhisperClient
from coop_bot.notificaciones.procesador import procesar_pendientes

logger = logging.getLogger(__name__)

_CLAVE_SESION = "sesion"
_INTERVALO_NOTIFICACIONES_SEGUNDOS = 60


def registrar_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("cancelar", on_cancelar))
    application.add_handler(MessageHandler(filters.VOICE, on_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))


def registrar_jobs(application: Application) -> None:
    """Procesa la cola de notificaciones pendientes en segundo plano.

    Nunca bloquea el flujo conversacional (ver ADR-010) — corre como job
    periódico independiente del diálogo con el operador.
    """
    if application.job_queue is None:
        return
    application.job_queue.run_repeating(
        _on_procesar_notificaciones,
        interval=_INTERVALO_NOTIFICACIONES_SEGUNDOS,
        first=_INTERVALO_NOTIFICACIONES_SEGUNDOS,
        name="procesar_notificaciones",
    )


async def _on_procesar_notificaciones(context: ContextTypes.DEFAULT_TYPE) -> None:
    resumen = await procesar_pendientes(_api_client(context), _notificador(context))
    if resumen.enviadas or resumen.fallidas:
        logger.info(
            "Cola de notificaciones procesada: %s enviadas, %s fallidas",
            resumen.enviadas,
            resumen.fallidas,
        )
    for error in resumen.errores:
        logger.warning("Error procesando la cola de notificaciones: %s", error)


# ── Handlers ─────────────────────────────────────────────────────────────────


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_operador(update, context):
        return
    chat_id = _chat_id(update)
    await enviar_texto(
        context,
        chat_id,
        "Hola Álvaro, soy tu asistente de la cooperativa BGC. "
        "Cuéntame por texto o nota de voz qué necesitas: registrar un aporte, "
        "un pago de cuota, un retiro, o consultarme el saldo de un socio, "
        "las cuotas pendientes de un crédito, o cuánto hay en caja.",
    )


async def on_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_operador(update, context):
        return
    chat_id = _chat_id(update)
    sesion = _obtener_sesion(context, chat_id)
    maquina = MaquinaEstados(sesion, _api_client(context))
    respuesta = maquina.cancelar_explicito()
    await _responder(context, chat_id, respuesta)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_operador(update, context):
        return
    if update.message is None or update.message.voice is None:
        return
    chat_id = _chat_id(update)

    archivo = await context.bot.get_file(update.message.voice.file_id)
    audio_bytes = bytes(await archivo.download_as_bytearray())

    try:
        texto = await _whisper_client(context).transcribir(audio_bytes)
    except Exception:  # noqa: BLE001 - cualquier falla de Whisper es recuperable
        logger.exception("Fallo al transcribir audio del chat %s", chat_id)
        await enviar_texto(context, chat_id, "No pude procesar tu nota de voz, intenta de nuevo.")
        return

    await _procesar_texto_entrante(update, context, texto)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _es_operador(update, context):
        return
    if update.message is None or update.message.text is None:
        return
    await _procesar_texto_entrante(update, context, update.message.text)


# ── Orquestación ─────────────────────────────────────────────────────────────


async def _procesar_texto_entrante(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str) -> None:
    chat_id = _chat_id(update)
    sesion = _obtener_sesion(context, chat_id)
    maquina = MaquinaEstados(sesion, _api_client(context))

    if sesion.estado == EstadoDialogo.ESPERANDO_DESAMBIGUACION:
        respuesta = await maquina.recibir_respuesta_desambiguacion(texto)
    elif sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION:
        respuesta = await maquina.recibir_confirmacion(texto)
    elif sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE:
        texto_para_llm = f"{sesion.texto_acumulado}. {texto}" if sesion.texto_acumulado else texto
        try:
            intencion = await _llm_client(context).interpretar(texto_para_llm)
        except Exception:  # noqa: BLE001 - cualquier falla del LLM es recuperable
            logger.exception("Fallo al interpretar mensaje del chat %s", chat_id)
            await enviar_texto(context, chat_id, "No pude interpretar tu mensaje, intenta de nuevo.")
            return
        respuesta = await maquina.procesar_intencion(intencion)
    else:
        await enviar_texto(context, chat_id, "Un momento, sigo procesando tu solicitud anterior.")
        return

    await _responder(context, chat_id, respuesta)


async def _responder(context: ContextTypes.DEFAULT_TYPE, chat_id: int, respuesta: RespuestaDialogo) -> None:
    await enviar_texto(context, chat_id, respuesta.texto)
    if respuesta.documento_pdf is not None and respuesta.nombre_documento is not None:
        await enviar_pdf(context, chat_id, respuesta.documento_pdf, respuesta.nombre_documento)
    if respuesta.cancelar_timeout:
        _cancelar_timeout(context, chat_id)
    if respuesta.requiere_timeout:
        _programar_timeout(context, chat_id)


async def _on_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None or job.chat_id is None:
        return
    chat_id = job.chat_id
    sesion = _sesion_existente(context)
    if sesion is None:
        return
    maquina = MaquinaEstados(sesion, _api_client(context))
    respuesta = maquina.cancelar_por_timeout()
    await enviar_texto(context, chat_id, respuesta.texto)


# ── Envío de mensajes ────────────────────────────────────────────────────────


async def enviar_texto(context: ContextTypes.DEFAULT_TYPE, chat_id: int, texto: str) -> None:
    await context.bot.send_message(chat_id=chat_id, text=texto)


async def enviar_pdf(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    contenido: bytes,
    nombre_archivo: str,
    caption: str | None = None,
) -> None:
    documento = InputFile(io.BytesIO(contenido), filename=nombre_archivo)
    await context.bot.send_document(chat_id=chat_id, document=documento, caption=caption)


# ── Timeout (5 minutos) ───────────────────────────────────────────────────────


def _nombre_job(chat_id: int) -> str:
    return f"timeout:{chat_id}"


def _programar_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    job_queue = context.job_queue
    if job_queue is None:
        return
    _cancelar_timeout(context, chat_id)
    job_queue.run_once(_on_timeout_job, when=TIMEOUT_SEGUNDOS, chat_id=chat_id, name=_nombre_job(chat_id))


def _cancelar_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    job_queue = context.job_queue
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(_nombre_job(chat_id)):
        job.schedule_removal()


# ── Sesión / clientes compartidos ─────────────────────────────────────────────


def _obtener_sesion(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> SesionDialogo:
    sesion = _sesion_existente(context)
    if sesion is not None:
        return sesion
    sesion = SesionDialogo(chat_id=chat_id)
    if context.chat_data is not None:
        context.chat_data[_CLAVE_SESION] = sesion
    return sesion


def _sesion_existente(context: ContextTypes.DEFAULT_TYPE) -> SesionDialogo | None:
    if context.chat_data is None:
        return None
    return cast(SesionDialogo | None, context.chat_data.get(_CLAVE_SESION))


def _api_client(context: ContextTypes.DEFAULT_TYPE) -> ApiClient:
    return cast(ApiClient, context.bot_data["api_client"])


def _whisper_client(context: ContextTypes.DEFAULT_TYPE) -> WhisperClient:
    return cast(WhisperClient, context.bot_data["whisper_client"])


def _llm_client(context: ContextTypes.DEFAULT_TYPE) -> LlmClient:
    return cast(LlmClient, context.bot_data["llm_client"])


def _notificador(context: ContextTypes.DEFAULT_TYPE) -> Notificador:
    return cast(Notificador, context.bot_data["notificador"])


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return cast(Config, context.bot_data["config"])


def _chat_id(update: Update) -> int:
    assert update.effective_chat is not None
    return int(update.effective_chat.id)


def _es_operador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat is None:
        return False
    return bool(update.effective_chat.id == _config(context).telegram_operador_chat_id)

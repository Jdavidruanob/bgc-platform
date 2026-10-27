"""Webhook público de Meta WhatsApp Cloud API para el asistente de socios
(ver ADR-011). Es, junto con `/health`, el único router sin `AuthDep` — la
autenticación la hace la firma HMAC de Meta, no el bearer token interno.

El `POST` es la única excepción `async def` en la API (ver ADR-009): hace
falta el cuerpo crudo del request para verificar `X-Hub-Signature-256` antes
de tocarlo, y eso solo se puede leer con `await request.body()`. El resto del
procesamiento (consultas de solo lectura) sigue siendo síncrono; solo el
armado del PDF de liquidación se delega a una `BackgroundTasks` para
responderle rápido a Meta.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.notificaciones_repo import NotificacionesRepository
from coop_core.repositories.socios_repo import SociosRepository
from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from coop_api.asistente import flujo
from coop_api.asistente.config import ConfigAsistente, desde_entorno
from coop_api.asistente.entrada import parsear_estados, parsear_mensajes
from coop_api.asistente.limite import limitador
from coop_api.asistente.whatsapp_cliente import ClienteWaDep, ClienteWhatsApp
from coop_api.deps import DbDep

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.get("/whatsapp")
def verificar(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Handshake de suscripción de Meta: hay que devolver `hub.challenge`
    como texto plano si el `hub.verify_token` coincide con el configurado."""
    cfg = desde_entorno()
    if (
        hub_mode == "subscribe"
        and cfg.verify_token
        and hub_verify_token is not None
        and hmac.compare_digest(hub_verify_token, cfg.verify_token)
    ):
        return Response(content=hub_challenge or "", media_type="text/plain")
    return Response(status_code=403)


@router.post("/whatsapp")
async def recibir(
    request: Request, background: BackgroundTasks, db: DbDep, cliente: ClienteWaDep
) -> Response:
    cfg = desde_entorno()
    cuerpo = await request.body()
    firma = request.headers.get("x-hub-signature-256")

    if not cfg.app_secret or not _firma_valida(cuerpo, firma, cfg.app_secret):
        logger.warning("Webhook de WhatsApp: firma inválida o ausente")
        return Response(status_code=403)

    try:
        payload = json.loads(cuerpo)
    except ValueError:
        logger.warning("Webhook de WhatsApp: cuerpo no es JSON válido")
        return Response(status_code=200)

    try:
        _procesar(db, cliente, background, cfg, payload)
    except Exception:
        # Nunca dejar que una excepción escape: un 500 hace que Meta
        # reintente en bucle, y el handler global (main.py) no loguea nada.
        logger.exception("Error procesando el webhook de WhatsApp")

    return Response(status_code=200)


def _procesar(
    db: DbConnection,
    cliente: ClienteWhatsApp,
    background: BackgroundTasks,
    cfg: ConfigAsistente,
    payload: Any,
) -> None:
    _registrar_estados(payload, db)
    socios_repo = SociosRepository(db)
    for mensaje in parsear_mensajes(payload):
        numero_e164 = mensaje.numero if mensaje.numero.startswith("+") else f"+{mensaje.numero}"
        enmascarado = f"***{numero_e164[-4:]}"
        logger.info("WhatsApp entrante de=%s tipo=%s wamid=%s", enmascarado, mensaje.tipo, mensaje.mensaje_id)

        if limitador.ya_visto(mensaje.mensaje_id):
            logger.info(
                "WhatsApp entrante repetido (reintento de Meta), se ignora wamid=%s", mensaje.mensaje_id
            )
            continue
        if mensaje.tipo == "ignorar" or not cfg.numero_autorizado(numero_e164):
            continue

        socio = socios_repo.find_by_whatsapp_e164(numero_e164)
        if socio is None:
            # Nunca contestarle a quien no es socio: esa respuesta automática
            # era la que alimentaba el ping-pong con otros bots (oct 2026).
            logger.info("WhatsApp de un número que no es socio (%s): no se responde", enmascarado)
            continue

        if not limitador.permitir(numero_e164):
            logger.warning(
                "WhatsApp: %s superó el tope de respuestas del asistente; no se responde", enmascarado
            )
            continue

        cliente.mostrar_escribiendo(mensaje.mensaje_id)
        flujo.atender(db, cliente, background, numero_e164, socio, mensaje)


def _registrar_estados(payload: Any, db: DbConnection) -> None:
    """Guarda en la notificación (por wamid) lo que Meta dice de los mensajes
    que enviamos, y lo deja en el log. Un 'failed' va a WARNING: es el caso en
    que Meta aceptó el envío pero no lo entregó (ej. 131042, 131049, 131026).
    El bot lee de ahí para avisarle al operador por Telegram.

    Un fallo al guardar nunca debe impedir atender los mensajes entrantes del
    asistente, que se procesan después con el mismo payload."""
    repo = NotificacionesRepository(db)
    for st in parsear_estados(payload):
        destino = st.destinatario[-4:]
        errores = "; ".join(st.errores)
        if st.estado == "failed":
            logger.warning(
                "WhatsApp NO entregado wamid=%s destino=***%s errores=%s",
                st.mensaje_id,
                destino,
                errores or "(sin detalle)",
            )
        else:
            logger.info("WhatsApp estado=%s wamid=%s destino=***%s", st.estado, st.mensaje_id, destino)
        try:
            if not repo.registrar_entrega(st.mensaje_id, st.estado, errores or None):
                logger.info("Estado '%s' de un wamid sin notificación (%s)", st.estado, st.mensaje_id)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("No se pudo guardar el estado de entrega de %s", st.mensaje_id)


def _firma_valida(cuerpo: bytes, firma_header: str | None, app_secret: str) -> bool:
    if not firma_header or not firma_header.startswith("sha256="):
        return False
    esperada = "sha256=" + hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma_header, esperada)

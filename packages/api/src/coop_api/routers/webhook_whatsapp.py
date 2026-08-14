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
from coop_core.repositories.socios_repo import SociosRepository
from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from coop_api.asistente import flujo
from coop_api.asistente.config import ConfigAsistente, desde_entorno
from coop_api.asistente.copy import numero_no_reconocido
from coop_api.asistente.entrada import parsear_mensajes
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
    socios_repo = SociosRepository(db)
    for mensaje in parsear_mensajes(payload):
        numero_e164 = mensaje.numero if mensaje.numero.startswith("+") else f"+{mensaje.numero}"
        if not cfg.numero_autorizado(numero_e164):
            continue

        socio = socios_repo.find_by_whatsapp_e164(numero_e164)
        if socio is None:
            cliente.enviar_texto(numero_e164, numero_no_reconocido())
            continue

        flujo.atender(db, cliente, background, numero_e164, socio, mensaje)


def _firma_valida(cuerpo: bytes, firma_header: str | None, app_secret: str) -> bool:
    if not firma_header or not firma_header.startswith("sha256="):
        return False
    esperada = "sha256=" + hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma_header, esperada)

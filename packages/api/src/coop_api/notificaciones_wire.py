"""Encola notificaciones de WhatsApp a los socios cuando se registra una
operación. Se llama desde cada endpoint de `operaciones.py` justo antes de
`db.commit()`, en la misma transacción — si la operación falla, no queda una
notificación huérfana.

Cada notificación guarda dos versiones del mismo aviso:

- `detalle`: la palabra genérica del documento adjunto ("recibo" o
  "liquidación"), que viaja como variable {{2}} de la plantilla de Meta (las
  variables no admiten saltos de línea ni tabulaciones). El detalle real de
  la operación (montos, cuotas) va solo en el PDF adjunto, no en el WhatsApp.
- `texto`: el mensaje completo ya redactado, que se usa cuando se envía como
  texto libre o cuando se cae al fallback wa.me.

Las notificaciones se crean como BORRADOR: no se envían solas. El bot le
pregunta al administrador si desea mandarle el comprobante al socio y, solo si
confirma, las aprueba (borrador → pendiente) para que el procesador las envíe.

Nunca bloquea ni falla la operación: si un socio no tiene número derivable, se
salta en silencio (no todos los socios tienen WhatsApp registrado aún).
"""

from __future__ import annotations

from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.notificaciones_repo import NotificacionesRepository
from coop_core.repositories.socios_repo import SociosRepository
from coop_core.utils.telefono import derivar_whatsapp_e164

_CIERRE = "¡Que tengas un excelente día!"

# Palabra genérica para {{2}} de la plantilla de Meta ("Aqui tienes tu {{2}}."),
# según el tipo de documento adjunto.
_DOCUMENTO_POR_TIPO = {"recibo": "recibo", "liquidacion": "liquidación"}


def _primer_nombre(nombres: Any) -> str:
    """'Pedro Antonio' → 'Pedro'. El saludo suena más natural con un solo
    nombre; si viene vacío se saluda sin nombre."""
    partes = str(nombres or "").strip().split()
    return partes[0].capitalize() if partes else ""


def _mensaje(nombres: Any, documento: str) -> str:
    """Arma el mensaje completo a partir de la misma palabra que viaja como
    variable {{2}} de la plantilla, para que ambas versiones digan lo mismo."""
    nombre = _primer_nombre(nombres)
    saludo = f"Hola {nombre} 👋" if nombre else "Hola 👋"
    return f"{saludo}\n\nAqui tienes tu {documento}.\n\n{_CIERRE}"


def _numero_de(socio: dict[str, Any]) -> str | None:
    return derivar_whatsapp_e164(
        socio.get("whatsapp_e164") if isinstance(socio, dict) else None,
        socio.get("celular") if isinstance(socio, dict) else None,
    )


def _socio_por_id(db: DbConnection, socio_id: int) -> dict[str, Any] | None:
    return SociosRepository(db).find_by_id(socio_id)


def _encolar(
    repo: NotificacionesRepository,
    socio_id: int,
    socio: dict[str, Any] | None,
    documento_tipo: str,
    documento_id: int,
) -> None:
    if socio is None:
        return
    numero = _numero_de(socio)
    if numero is None:
        return
    documento = _DOCUMENTO_POR_TIPO[documento_tipo]
    texto = _mensaje(socio.get("nombres"), documento)
    # Se crea como BORRADOR: no se envía hasta que el administrador lo apruebe
    # desde el chat del bot (ver ADR-010 y el flujo de confirmación).
    repo.create(socio_id, numero, texto, documento_tipo, documento_id, documento, estado="borrador")


def _notificar_recibo(db: DbConnection, recibi_de: dict[str, Any], recibo_id: int) -> None:
    """Encola UNA sola notificación por recibo, dirigida únicamente al socio
    que aparece como 'recibí de'. Un recibo puede tener varias líneas (p. ej.
    un aporte familiar registra una por cada miembro), pero solo quien
    entregó el dinero debe recibir el WhatsApp — nunca los demás socios que
    aparecen como líneas del mismo recibo."""
    repo = NotificacionesRepository(db)
    _encolar(repo, int(recibi_de["id"]), recibi_de, "recibo", recibo_id)


def notificar_aportes(db: DbConnection, resultado: dict[str, Any], recibi_de: dict[str, Any]) -> None:
    _notificar_recibo(db, recibi_de, int(resultado["recibo_id"]))


def notificar_retiro(db: DbConnection, resultado: dict[str, Any], socio: dict[str, Any]) -> None:
    _notificar_recibo(db, socio, int(resultado["recibo_id"]))


def notificar_pagos(db: DbConnection, resultado: dict[str, Any], recibi_de: dict[str, Any]) -> None:
    _notificar_recibo(db, recibi_de, int(resultado["recibo_id"]))


def notificar_combinado(db: DbConnection, resultado: dict[str, Any], recibi_de: dict[str, Any]) -> None:
    _notificar_recibo(db, recibi_de, int(resultado["recibo_id"]))


def notificar_credito_nuevo(db: DbConnection, resultado: dict[str, Any]) -> None:
    """El crédito no genera fila en `recibos`, pero sí una liquidación: se
    adjunta esa (documento_tipo='liquidacion', documento_id=letra_id)."""
    repo = NotificacionesRepository(db)
    letra_id = int(resultado["letra_id"])
    for s in resultado["socios"]:
        socio_id = int(s["id"])
        _encolar(repo, socio_id, _socio_por_id(db, socio_id), "liquidacion", letra_id)

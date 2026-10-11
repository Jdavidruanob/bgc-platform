"""Parseo del sobre entrante del webhook de Meta WhatsApp Cloud API.

Puro: no hace I/O, no lanza excepciones ante un payload mal formado — un
sobre inesperado simplemente produce una lista vacía. Ver
developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components para la
forma exacta de cada tipo de mensaje.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TipoMensaje = Literal["texto", "boton", "otro"]


@dataclass(frozen=True)
class MensajeEntrante:
    numero: str
    """Tal como lo manda Meta: dígitos sin '+' (ej. '573001234567')."""
    tipo: TipoMensaje
    texto: str = ""
    boton_id: str = ""


def parsear_mensajes(payload: Any) -> list[MensajeEntrante]:
    """Extrae los mensajes entrantes de un sobre de webhook. Ignora
    `statuses` (ver `parsear_estados`) y cualquier
    estructura que no sea la esperada."""
    mensajes: list[MensajeEntrante] = []
    if not isinstance(payload, dict):
        return mensajes

    for entry in _lista(payload.get("entry")):
        if not isinstance(entry, dict):
            continue
        for change in _lista(entry.get("changes")):
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            for msg in _lista(value.get("messages")):
                mensaje = _parsear_uno(msg)
                if mensaje is not None:
                    mensajes.append(mensaje)
    return mensajes


@dataclass(frozen=True)
class EstadoMensaje:
    """Confirmación de Meta sobre un mensaje que NOSOTROS enviamos."""

    mensaje_id: str
    estado: str
    """'sent' | 'delivered' | 'read' | 'failed'."""
    destinatario: str = ""
    errores: tuple[str, ...] = ()
    """Cada uno como 'codigo: titulo'. Solo viene con 'failed'."""


def parsear_estados(payload: Any) -> list[EstadoMensaje]:
    """Extrae los `statuses` de un sobre de webhook. Es la única forma de
    saber si un mensaje aceptado por Meta (HTTP 200 al enviarlo) realmente se
    entregó. Igual que `parsear_mensajes`, nunca lanza ante un sobre raro."""
    estados: list[EstadoMensaje] = []
    if not isinstance(payload, dict):
        return estados
    for entry in _lista(payload.get("entry")):
        if not isinstance(entry, dict):
            continue
        for change in _lista(entry.get("changes")):
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            for st in _lista(value.get("statuses")):
                if not isinstance(st, dict) or not st.get("id") or not st.get("status"):
                    continue
                errores = tuple(
                    f"{e.get('code')}: {e.get('title') or e.get('message') or ''}"
                    for e in _lista(st.get("errors"))
                    if isinstance(e, dict)
                )
                estados.append(
                    EstadoMensaje(
                        mensaje_id=str(st["id"]),
                        estado=str(st["status"]),
                        destinatario=str(st.get("recipient_id") or ""),
                        errores=errores,
                    )
                )
    return estados


def _lista(valor: Any) -> list[Any]:
    return valor if isinstance(valor, list) else []


def _parsear_uno(msg: Any) -> MensajeEntrante | None:
    if not isinstance(msg, dict):
        return None
    numero = msg.get("from")
    if not isinstance(numero, str) or not numero:
        return None

    tipo = msg.get("type")

    if tipo == "text":
        texto = msg.get("text", {})
        cuerpo = texto.get("body") if isinstance(texto, dict) else None
        return MensajeEntrante(numero=numero, tipo="texto", texto=str(cuerpo or ""))

    if tipo == "interactive":
        interactive = msg.get("interactive", {})
        if not isinstance(interactive, dict):
            return MensajeEntrante(numero=numero, tipo="otro")
        sub_tipo = interactive.get("type")
        if sub_tipo == "button_reply":
            reply = interactive.get("button_reply", {})
        elif sub_tipo == "list_reply":
            reply = interactive.get("list_reply", {})
        else:
            return MensajeEntrante(numero=numero, tipo="otro")
        boton_id = reply.get("id") if isinstance(reply, dict) else None
        if not boton_id:
            return MensajeEntrante(numero=numero, tipo="otro")
        return MensajeEntrante(numero=numero, tipo="boton", boton_id=str(boton_id))

    if tipo == "button":
        # Quick-reply de una plantilla con botones (no las usamos hoy, pero
        # Meta puede mandarlas si alguna vez se combina con recordatorios).
        boton = msg.get("button", {})
        payload_boton = boton.get("payload") if isinstance(boton, dict) else None
        if not payload_boton:
            return MensajeEntrante(numero=numero, tipo="otro")
        return MensajeEntrante(numero=numero, tipo="boton", boton_id=str(payload_boton))

    # audio (incluye notas de voz), image, video, document, sticker,
    # location, contacts, reaction, system, unsupported, etc.
    return MensajeEntrante(numero=numero, tipo="otro")

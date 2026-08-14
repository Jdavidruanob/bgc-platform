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
    """Extrae los mensajes entrantes de un sobre de webhook. Ignora en
    silencio `statuses` (confirmaciones de entrega/lectura) y cualquier
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

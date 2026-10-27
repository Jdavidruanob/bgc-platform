"""Avisos al operador sobre lo que REALMENTE pasó con un mensaje de WhatsApp.

Meta responde HTTP 200 cuando *acepta* un envío, pero entregarlo es otra cosa:
el resultado llega después por webhook (`statuses`) a la API, que lo guarda en
la notificación. Este módulo lee esos resultados y redacta el aviso de
Telegram: llegó, no llegó (y por qué), o Meta nunca dijo nada.
"""

from __future__ import annotations

import json
import logging

from coop_contracts.respuestas import EntregaPorAvisar

from coop_bot.api.cliente import ApiClient, ApiError

logger = logging.getLogger(__name__)

# Códigos de error de WhatsApp Cloud API → qué significa para el operador.
_MOTIVOS: dict[str, str] = {
    "131042": "problema de pago en la cuenta de WhatsApp Business (revisa el método de pago en Meta)",
    "131026": "el número no tiene WhatsApp o no se puede entregar a ese número",
    "131049": "Meta decidió no entregar el mensaje (calidad de la plantilla o límites de Meta)",
    "131047": "pasaron más de 24 horas desde que el socio escribió y no se usó una plantilla",
    "131048": "Meta limitó los envíos por spam",
    "131051": "tipo de mensaje no soportado",
    "131053": "no se pudo subir el archivo adjunto",
    "130429": "se superó el límite de envíos por segundo",
    "132000": "la plantilla recibió una cantidad de variables distinta a la que espera",
    "132001": "la plantilla no existe (revisa el nombre y el idioma)",
    "132005": "el texto de la plantilla traducido es demasiado largo",
    "132007": "el contenido de la plantilla incumple las políticas de Meta",
    "132012": "los parámetros de la plantilla no tienen el formato esperado",
    "132015": "la plantilla está pausada por baja calidad",
    "132016": "la plantilla está deshabilitada",
}


def traducir_error_meta(error: str | None) -> str:
    """`error` viene como 'codigo: titulo'. Devuelve una explicación en español;
    si el código no está en la tabla, deja el texto original de Meta."""
    if not error:
        return "Meta no dio detalle del motivo"
    codigo = error.split(":", 1)[0].strip()
    motivo = _MOTIVOS.get(codigo)
    if motivo:
        return f"{motivo} [error {codigo}]"
    return f"{error}"


def _que_era(entrega: EntregaPorAvisar) -> str:
    """Cómo nombrar lo que se mandó: no es lo mismo un recordatorio de cuota
    que un comprobante (ver el feedback del usuario en `telegram.py`)."""
    if entrega.documento_tipo == "recordatorio_cuota":
        datos: dict[str, str] = {}
        if entrega.detalle:
            try:
                datos = json.loads(entrega.detalle)
            except ValueError:
                datos = {}
        cuota, letra = datos.get("numero_cuota"), datos.get("numero_letra")
        if cuota and letra:
            return f"el recordatorio de la cuota #{cuota} del crédito #{letra}"
        return "el recordatorio de cuota"
    return "su comprobante"


def texto_entregas(entregas: list[EntregaPorAvisar]) -> str:
    """Aviso para el operador. Vacío si no hay nada que reportar."""
    llegaron = [e for e in entregas if e.resultado == "delivered"]
    fallaron = [e for e in entregas if e.resultado == "failed"]
    sin_confirmar = [e for e in entregas if e.resultado == "sin_confirmacion"]

    bloques: list[str] = []
    if llegaron:
        bloques.append(
            "✅ Ya les llegó por WhatsApp:\n"
            + "\n".join(f"• {e.socio_nombre}: {_que_era(e)}" for e in llegaron)
        )
    if fallaron:
        bloques.append(
            "⚠️ NO les llegó por WhatsApp:\n"
            + "\n".join(
                f"• {e.socio_nombre}: {_que_era(e)} — {traducir_error_meta(e.error)}" for e in fallaron
            )
        )
    if sin_confirmar:
        bloques.append(
            "❓ Meta aceptó el mensaje pero no confirmó la entrega (pueden no haberlo recibido):\n"
            + "\n".join(f"• {e.socio_nombre}: {_que_era(e)}" for e in sin_confirmar)
        )
    return "\n\n".join(bloques)


async def consultar_entregas(cliente: ApiClient) -> tuple[str, list[int], list[str]]:
    """(texto del aviso, ids incluidos, nombres de los socios). Si la API no responde devuelve vacío:
    se reintenta en el siguiente ciclo, no se pierde nada."""
    try:
        respuesta = await cliente.get_entregas_por_avisar()
    except ApiError as exc:
        logger.warning("No se pudo consultar las entregas de WhatsApp: %s", exc.mensaje)
        return "", [], []
    entregas = respuesta.entregas
    return texto_entregas(entregas), [e.id for e in entregas], [e.socio_nombre for e in entregas]

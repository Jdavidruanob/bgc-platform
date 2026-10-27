"""Redacta los avisos de Telegram al operador con el tono de un asistente
personal ("Buenos días Álvaro, ya les envié…") usando el LLM, para que no
lleguen siempre con la misma plantilla fija.

El LLM solo reescribe: los hechos salen del texto fijo que arma el bot. Si la
respuesta pierde un nombre o un número del original, o el LLM falla o tarda,
se manda el texto fijo tal cual — un aviso de dinero nunca depende del LLM.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ZONA = ZoneInfo("America/Bogota")
_TIMEOUT_SEGUNDOS = 15.0

_PROMPT = """Eres el asistente personal de la tesorería de la Cooperativa BGC, una \
cooperativa familiar de ahorro y crédito en Colombia. Le escribes por Telegram al \
tesorero{nombre} para contarle lo que acabas de hacer por WhatsApp con los socios.

Reescribe el aviso que te paso con un tono cercano, cálido y natural, en español \
colombiano, como lo haría una persona de confianza. Saluda según la hora ({momento}) \
y varía la forma de decirlo: que no suene a plantilla.

Reglas estrictas:
- Conserva TODOS los nombres de socios, números de cuota, de crédito, fechas, \
montos y códigos de error exactamente como vienen. No inventes nada ni agregues datos.
- Si hay algo que NO llegó o falló, dilo con claridad y sin minimizarlo.
- Mantén una línea por socio (puedes usar viñetas). Máximo 2 emojis en total.
- Sé breve: un saludo corto, el contenido y, si quieres, una frase final corta.
- Responde solo con el mensaje, sin comillas ni explicaciones."""


class Completador(Protocol):
    async def completar(self, sistema: str, usuario: str) -> str | None: ...


def _momento(ahora: datetime) -> str:
    if ahora.hour < 12:
        return "es de mañana"
    if ahora.hour < 19:
        return "es de tarde"
    return "es de noche"


def _numeros(texto: str) -> set[str]:
    return set(re.findall(r"\d[\d.,/:-]*\d|\d", texto))


def conserva_hechos(original: str, redactado: str, nombres: list[str]) -> bool:
    """True si el texto redactado conserva cada número del original y el
    nombre completo de cada socio."""
    plano = redactado.replace("\u00a0", " ")
    return all(n in plano for n in _numeros(original)) and all(n in plano for n in nombres)


async def redactar(
    texto: str,
    completador: Completador | None,
    nombres: list[str],
    nombre_operador: str | None = None,
    ahora: datetime | None = None,
) -> str:
    """El aviso reescrito por el LLM, o `texto` sin cambios si algo sale mal."""
    if not texto or completador is None:
        return texto
    momento = _momento(ahora or datetime.now(_ZONA))
    sistema = _PROMPT.format(nombre=f" ({nombre_operador})" if nombre_operador else "", momento=momento)
    try:
        redactado = await asyncio.wait_for(completador.completar(sistema, texto), _TIMEOUT_SEGUNDOS)
    except Exception:  # noqa: BLE001 - el LLM nunca debe tumbar un aviso
        logger.warning("No se pudo redactar el aviso con el LLM; se envía el texto fijo", exc_info=True)
        return texto
    if not isinstance(redactado, str) or not redactado.strip():
        return texto
    redactado = redactado.strip()
    if not conserva_hechos(texto, redactado, nombres):
        logger.warning("El LLM cambió o perdió datos del aviso; se envía el texto fijo")
        return texto
    return redactado

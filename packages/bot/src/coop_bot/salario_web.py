"""Consulta best-effort del salario mínimo vigente en Colombia desde la web.

Es deliberadamente defensivo: si la página cambia, no responde, o el valor no es
plausible, devuelve None y el flujo usa el valor guardado. Además el operador
SIEMPRE confirma o corrige el monto antes de generar el recibo, así que un valor
web equivocado nunca llega al documento sin revisión.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Rango plausible de un salario mínimo mensual colombiano (COP). Fuera de esto
# se descarta el valor.
_MIN = 1_000_000
_MAX = 3_000_000

_URL = "https://es.wikipedia.org/wiki/Salario_m%C3%ADnimo_en_Colombia"


async def consultar_salario_minimo_web(timeout: float = 8.0) -> int | None:
    """Devuelve el salario mínimo leído de la web, o None si no se pudo obtener
    un valor confiable."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cliente:
            resp = await cliente.get(_URL, headers={"User-Agent": "Mozilla/5.0 (BGC-bot)"})
            resp.raise_for_status()
        plausibles = [m for m in _extraer_montos(resp.text) if _MIN <= m <= _MAX]
        if plausibles:
            # Heurística: el mayor monto plausible suele ser el vigente. El
            # operador confirma de todos modos.
            return max(plausibles)
    except Exception:  # noqa: BLE001 - cualquier fallo => usamos el valor guardado
        logger.warning("No se pudo consultar el salario mínimo en la web", exc_info=True)
    return None


def _extraer_montos(texto: str) -> list[int]:
    """Extrae montos con separador de miles por puntos (ej: 1.423.500)."""
    montos: list[int] = []
    for crudo in re.findall(r"[1-9](?:\.\d{3}){2}", texto):
        try:
            montos.append(int(crudo.replace(".", "")))
        except ValueError:
            continue
    return montos

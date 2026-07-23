"""Resolución de nombres mencionados por el operador hacia IDs de socio/letra.

Regla general: 0 resultados -> no encontrado, 1 resultado -> se autoselecciona,
2+ resultados -> se le pregunta al operador. En un flujo que mueve dinero no
se adivina ante ambigüedad, aunque el mock devuelva un `score` de fuzzy match.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from coop_contracts.respuestas import (
    CreditoResumen,
    SocioSearchItem,
)

from coop_bot.api.cliente import ApiClient


@dataclass(frozen=True)
class SocioResuelto:
    id: int
    nombre_completo: str
    saldo: int


@dataclass
class ResolucionSocio:
    query: str
    estado: Literal["resuelto", "no_encontrado", "ambiguo"]
    resuelto: SocioResuelto | None = None
    candidatos: list[SocioSearchItem] = field(default_factory=list)


@dataclass
class ResolucionLetra:
    socio_id: int
    estado: Literal["resuelto", "no_encontrado", "ambiguo"]
    letra_id: int | None = None
    candidatos: list[CreditoResumen] = field(default_factory=list)


_UMBRAL_SCORE_GANADOR = 0.75
_UMBRAL_BRECHA_GANADOR = 0.15


async def resolver_socio(cliente: ApiClient, nombre: str) -> ResolucionSocio:
    resp = await cliente.buscar_socios(nombre)
    candidatos = resp.socios

    if not candidatos:
        return ResolucionSocio(query=nombre, estado="no_encontrado")

    if len(candidatos) == 1:
        return await _resolver_unico(cliente, nombre, candidatos[0])

    if _tiene_ganador_claro(candidatos):
        return await _resolver_unico(cliente, nombre, candidatos[0])

    return ResolucionSocio(query=nombre, estado="ambiguo", candidatos=candidatos)


async def _resolver_unico(cliente: ApiClient, nombre: str, elegido: SocioSearchItem) -> ResolucionSocio:
    detalle = await cliente.get_socio(elegido.id)
    resuelto = SocioResuelto(
        id=elegido.id,
        nombre_completo=elegido.nombre_completo,
        saldo=detalle.saldo,
    )
    return ResolucionSocio(query=nombre, estado="resuelto", resuelto=resuelto)


def _tiene_ganador_claro(candidatos: list[SocioSearchItem]) -> bool:
    """Auto-selección cuando el mejor candidato es claramente superior.

    Con el fuzzy que prioriza el nombre de pila, el ganador correcto le saca una
    brecha amplia al resto incluso cuando comparten apellidos. Basta con un score
    razonable (>= 0.75) y una brecha >= 0.15 sobre el segundo. Homónimos reales
    (dos socios que coinciden igual de bien) quedan empatados y sí se preguntan.
    """
    mejor, segundo = candidatos[0], candidatos[1]
    if mejor.score < _UMBRAL_SCORE_GANADOR:
        return False
    return (mejor.score - segundo.score) >= _UMBRAL_BRECHA_GANADOR


async def resolver_letra(cliente: ApiClient, socio_id: int, letra_hint: str | None) -> ResolucionLetra:
    if letra_hint is not None:
        letra_id = _parsear_letra_hint(letra_hint)
        if letra_id is not None:
            # Se confía en el hint: la API ya valida la letra en el endpoint
            # de escritura (LETRA_NO_ENCONTRADA), no hace falta un pre-chequeo.
            return ResolucionLetra(socio_id=socio_id, estado="resuelto", letra_id=letra_id)

    resp = await cliente.get_creditos_socio(socio_id)
    creditos = resp.creditos

    if not creditos:
        return ResolucionLetra(socio_id=socio_id, estado="no_encontrado")

    if len(creditos) == 1:
        return ResolucionLetra(socio_id=socio_id, estado="resuelto", letra_id=creditos[0].letra_id)

    return ResolucionLetra(socio_id=socio_id, estado="ambiguo", candidatos=creditos)


def _parsear_letra_hint(letra_hint: str) -> int | None:
    texto = letra_hint.strip().lstrip("#").removeprefix("letra").strip()
    return int(texto) if texto.isdigit() else None


def formatear_lista_socios(candidatos: Sequence[SocioSearchItem]) -> str:
    lineas = [f"{i}. {c.nombre_completo}" for i, c in enumerate(candidatos, start=1)]
    return "\n".join(lineas) + "\nResponde con el número de la opción correcta."


def formatear_lista_letras(candidatos: Sequence[CreditoResumen]) -> str:
    lineas = [
        f"{i}. Letra {c.letra_id} (capital original: {c.capital_original})"
        for i, c in enumerate(candidatos, start=1)
    ]
    return "\n".join(lineas) + "\nResponde con el número de la opción correcta."


_ORDINALES_ES: dict[str, int] = {
    "uno": 1,
    "primero": 1,
    "primera": 1,
    "primer": 1,
    "dos": 2,
    "segundo": 2,
    "segunda": 2,
    "tres": 3,
    "tercero": 3,
    "tercera": 3,
    "tercer": 3,
    "cuatro": 4,
    "cuarto": 4,
    "cuarta": 4,
    "cinco": 5,
    "quinto": 5,
    "quinta": 5,
    "seis": 6,
    "sexto": 6,
    "sexta": 6,
    "siete": 7,
    "septimo": 7,
    "séptimo": 7,
    "séptima": 7,
    "ocho": 8,
    "octavo": 8,
    "octava": 8,
    "nueve": 9,
    "noveno": 9,
    "novena": 9,
    "diez": 10,
    "decimo": 10,
    "décimo": 10,
    "décima": 10,
}


def parsear_seleccion(texto: str, n_opciones: int) -> int | None:
    """Convierte selección del operador a índice 0-based. None si no es válida.

    Acepta: "1", "1.", "1)", "el 1", "el primero", "primero", "uno",
    o el nombre exacto/parcial que aparece en la lista mostrada.
    """
    limpio = texto.strip().lower().rstrip(".)-").lstrip("(")
    if limpio.startswith("el "):
        limpio = limpio[3:].strip()
    if limpio.startswith("la "):
        limpio = limpio[3:].strip()

    if limpio.isdigit():
        indice = int(limpio) - 1
        if 0 <= indice < n_opciones:
            return indice
        return None

    if limpio in _ORDINALES_ES:
        indice = _ORDINALES_ES[limpio] - 1
        if 0 <= indice < n_opciones:
            return indice
        return None

    return None

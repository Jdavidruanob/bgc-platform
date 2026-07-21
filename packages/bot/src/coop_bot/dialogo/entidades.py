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


async def resolver_socio(cliente: ApiClient, nombre: str) -> ResolucionSocio:
    resp = await cliente.buscar_socios(nombre)
    candidatos = resp.socios

    if not candidatos:
        return ResolucionSocio(query=nombre, estado="no_encontrado")

    if len(candidatos) == 1:
        elegido = candidatos[0]
        detalle = await cliente.get_socio(elegido.id)
        resuelto = SocioResuelto(
            id=elegido.id,
            nombre_completo=elegido.nombre_completo,
            saldo=detalle.saldo,
        )
        return ResolucionSocio(query=nombre, estado="resuelto", resuelto=resuelto)

    return ResolucionSocio(query=nombre, estado="ambiguo", candidatos=candidatos)


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


def parsear_seleccion(texto: str, n_opciones: int) -> int | None:
    """Convierte '1'..'n' a un índice 0-based. None si no es válido."""
    limpio = texto.strip()
    if not limpio.isdigit():
        return None
    indice = int(limpio) - 1
    if 0 <= indice < n_opciones:
        return indice
    return None

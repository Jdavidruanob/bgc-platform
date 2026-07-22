"""Búsqueda fuzzy de socios usando rapidfuzz.

El operador dicta un nombre por voz o texto. El nombre de pila importa más que
el apellido porque en la cooperativa hay muchos socios con los mismos apellidos
(por parentesco). "Maritza Padilla" debe ganarle a "Fanny Padilla Jojoa" aunque
comparten apellido: la palabra "Maritza" es lo que la desambigua.

Estrategia:
- Comparar la query contra nombres y apellidos por separado.
- El score compuesto es promedio ponderado 70% nombres, 30% apellidos.
- Se compara también contra el nombre completo para no perder matches globales.
- Se elige el máximo entre el compuesto y el global.
- Un match exacto o de substring da bonus explícito.
"""

from __future__ import annotations

import unicodedata

from rapidfuzz import fuzz

_PESO_NOMBRES = 0.7
_PESO_APELLIDOS = 0.3


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, espacios colapsados. Whisper a veces mete
    espacios raros ("Marit Zapadilla") — este preproceso ayuda pero no lo cura.
    """
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())


def score_nombre(query: str, nombres: str, apellidos: str) -> float:
    q = _normalizar(query)
    n = _normalizar(nombres)
    a = _normalizar(apellidos)
    completo = f"{n} {a}".strip()

    if not q:
        return 0.0

    if q == completo:
        return 1.0
    if q in completo:
        return 0.92

    score_n = fuzz.token_set_ratio(q, n) / 100.0
    score_a = fuzz.token_set_ratio(q, a) / 100.0
    compuesto = _PESO_NOMBRES * score_n + _PESO_APELLIDOS * score_a

    # Deliberadamente NO se usa partial_ratio contra el nombre completo: premia
    # subcadenas contiguas como "padilla" y termina favoreciendo apellidos
    # comunes sobre coincidencias reales de nombre de pila.
    ratio_global = fuzz.token_sort_ratio(q, completo) / 100.0

    return round(max(compuesto, ratio_global), 4)


def buscar_socios(
    socios: list[dict[str, object]],
    query: str,
    limit: int = 10,
    umbral: float = 0.50,
) -> list[tuple[dict[str, object], float]]:
    resultados = [(s, score_nombre(query, str(s["nombres"]), str(s["apellidos"]))) for s in socios]
    resultados = [(s, sc) for s, sc in resultados if sc >= umbral]
    resultados.sort(key=lambda x: x[1], reverse=True)
    return resultados[:limit]

"""Búsqueda fuzzy de socios usando rapidfuzz."""

from __future__ import annotations

from rapidfuzz import fuzz


def score_nombre(query: str, nombres: str, apellidos: str) -> float:
    nombre_completo = f"{nombres} {apellidos}".lower()
    q = query.lower().strip()
    if q == nombre_completo:
        return 1.0
    if q in nombre_completo:
        return 0.92
    ratio = fuzz.token_sort_ratio(q, nombre_completo) / 100.0
    partial = fuzz.partial_ratio(q, nombre_completo) / 100.0
    return round(max(ratio, partial * 0.9), 4)


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

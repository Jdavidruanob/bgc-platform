"""Búsqueda fuzzy de socios usando rapidfuzz.

El operador dicta un nombre por voz o texto. El nombre de pila importa mucho más
que el apellido porque en la cooperativa hay muchos socios con los mismos
apellidos (por parentesco). "Maritza Padilla Jojoa" debe ganarle con amplitud a
"Fanny Padilla Jojoa" aunque comparten los dos apellidos: la palabra "Maritza"
es lo único que las distingue.

Estrategia:
- Si la query es igual o subcadena del nombre completo, match casi perfecto.
- Si no, el score combina dos señales:
  - `match_nombre`: qué tan bien el nombre de pila de la query (primer token)
    coincide con ALGÚN nombre de pila del candidato. Es el gran discriminador.
  - `match_full`: solapamiento de tokens de la query con el nombre completo.
  El nombre de pila pesa fuerte (0.45) para que dos socios con los mismos
  apellidos no queden empatados: gana quien además comparte el nombre.
"""

from __future__ import annotations

import unicodedata

from rapidfuzz import fuzz

_PESO_FULL = 0.55
_PESO_NOMBRE = 0.45


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
        return 0.95

    q_tokens = q.split()
    nombre_tokens = n.split() or [""]
    apellido_tokens = a.split() or [""]

    # match_nombre: qué tan bien el nombre de pila de la query coincide con el
    # del candidato. Se prueba el primer token contra cada nombre, y también las
    # dos primeras palabras unidas contra el nombre unido: así "max eider" pega
    # con "magceider" (Whisper parte los nombres raros en dos).
    nombre_unido = n.replace(" ", "")
    variantes = [q_tokens[0]]
    if len(q_tokens) >= 2:
        variantes.append(q_tokens[0] + q_tokens[1])
    match_nombre = max(fuzz.ratio(v, nombre_unido) for v in variantes) / 100.0
    match_nombre = max(
        match_nombre,
        max(fuzz.ratio(q_tokens[0], nt) for nt in nombre_tokens) / 100.0,
    )

    # match_apellido: el mejor parecido de CUALQUIER token de la query con algún
    # apellido del candidato. Rescata a los que comparten apellido cuando el
    # nombre viene distorsionado ("Magceider García" -> "Max Eider García").
    match_apellido = max((fuzz.ratio(x, y) for x in q_tokens for y in apellido_tokens), default=0) / 100.0

    match_full = fuzz.token_set_ratio(q, completo) / 100.0

    base = _PESO_FULL * match_full + _PESO_NOMBRE * match_nombre
    # Ruta por apellido cuando el nombre no cuadra pero el apellido sí.
    ruta_apellido = 0.55 * match_apellido + 0.35 * match_nombre
    # Premia cuando nombre Y apellido coinciden (el candidato correcto real).
    nombre_y_apellido = 0.5 * match_nombre + 0.5 * match_apellido

    return round(max(base, ruta_apellido, nombre_y_apellido), 4)


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

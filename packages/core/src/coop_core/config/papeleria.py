PAPELERIA_POR_APORTE: int = 3000

# IDs de socios que no pagan papelería (administración).
# Actualmente todos pagan: no hay exentos.
SOCIOS_EXENTOS_PAPELERIA: frozenset[int] = frozenset()


def es_cobrable(socio_id: int) -> bool:
    return socio_id not in SOCIOS_EXENTOS_PAPELERIA


def count_cobrables(socio_ids: list[int]) -> int:
    return sum(1 for sid in socio_ids if es_cobrable(sid))

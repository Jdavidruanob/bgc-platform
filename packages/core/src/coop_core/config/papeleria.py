PAPELERIA_POR_APORTE: int = 3000

# IDs de socios que no pagan papelería (administración). Corresponden a los
# nombres de la BGC-software.db (IDs preservados en el seed):
#   1 Alvaro Lizardo Burbano Garcia
#   2 Maritza Del S. Padilla Jojoa
#   3 Nathalia Soledad Burbano Padilla
#   4 Jose David Ruano Burbano
#   5 Julieta Hoyos Burbano
SOCIOS_EXENTOS_PAPELERIA: frozenset[int] = frozenset({1, 2, 3, 4, 5})


def es_cobrable(socio_id: int) -> bool:
    return socio_id not in SOCIOS_EXENTOS_PAPELERIA


def count_cobrables(socio_ids: list[int]) -> int:
    return sum(1 for sid in socio_ids if es_cobrable(sid))

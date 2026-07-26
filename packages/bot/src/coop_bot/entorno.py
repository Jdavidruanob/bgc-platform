"""En qué entorno corre el bot: producción o pruebas.

El bot no habla con la base de datos: habla con la API, y es la API la que
decide contra qué base escribe. Así que aquí "entorno" significa *contra qué
API estoy hablando*, y se declara con la variable `APP_ENV`.

Si `APP_ENV` no está definida se asume **producción**. Es el default prudente:
creer que se está en pruebas cuando en realidad se está moviendo plata real es
el error que hay que evitar.
"""

from __future__ import annotations

import os

PRODUCCION = "produccion"
PRUEBAS = "pruebas"

_ALIAS = {
    "produccion": PRODUCCION,
    "producción": PRODUCCION,
    "prod": PRODUCCION,
    "production": PRODUCCION,
    "live": PRODUCCION,
    "real": PRODUCCION,
    "pruebas": PRUEBAS,
    "prueba": PRUEBAS,
    "dev": PRUEBAS,
    "desarrollo": PRUEBAS,
    "development": PRUEBAS,
    "test": PRUEBAS,
    "testing": PRUEBAS,
    "staging": PRUEBAS,
    "local": PRUEBAS,
}

# Encabezado que se antepone a cada respuesta del bot cuando NO es producción.
AVISO_PRUEBAS = "🧪 MODO PRUEBAS — esto no afecta la base real\n\n"


def get_entorno(valor: str | None = None) -> str:
    """`PRODUCCION` o `PRUEBAS`. Sin argumento, lee `APP_ENV` del entorno."""
    crudo = valor if valor is not None else os.environ.get("APP_ENV")
    if not crudo:
        return PRODUCCION
    return _ALIAS.get(crudo.strip().lower(), PRODUCCION)


def es_produccion(valor: str | None = None) -> bool:
    return get_entorno(valor) == PRODUCCION


def es_pruebas(valor: str | None = None) -> bool:
    return get_entorno(valor) == PRUEBAS


def etiqueta(valor: str | None = None) -> str:
    return "PRODUCCIÓN" if es_produccion(valor) else "PRUEBAS"


def prefijo(valor: str | None = None) -> str:
    """Encabezado a anteponer a un mensaje. Vacío en producción."""
    return "" if es_produccion(valor) else AVISO_PRUEBAS

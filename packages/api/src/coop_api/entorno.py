"""En qué entorno corre la API: producción o pruebas.

La API es quien realmente escribe en la base, así que aquí el entorno importa
más que en ningún otro lado. Se declara con `APP_ENV`; si no está, se deduce
del puerto de `DATABASE_URL` y, si tampoco se reconoce, se asume **producción**
por prudencia.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

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

# Bases conocidas por host:puerto. Ambas viven en el mismo host de Railway;
# lo que las distingue es el puerto.
_BASES_CONOCIDAS = {
    "sakura.proxy.rlwy.net:42792": PRODUCCION,
    "sakura.proxy.rlwy.net:54722": PRUEBAS,
}


def _host_puerto(dsn: str) -> str:
    """'host:puerto' de la URL, sin credenciales. Cadena vacía si no se puede leer."""
    try:
        p = urlparse(dsn)
        if not p.hostname:
            return ""
        return f"{p.hostname}:{p.port}" if p.port else p.hostname
    except Exception:
        return ""


def get_entorno() -> str:
    declarado = _ALIAS.get((os.environ.get("APP_ENV") or "").strip().lower())
    if declarado:
        return declarado
    return _BASES_CONOCIDAS.get(_host_puerto(os.environ.get("DATABASE_URL", "")), PRODUCCION)


def es_produccion() -> bool:
    return get_entorno() == PRODUCCION


def es_pruebas() -> bool:
    return get_entorno() == PRUEBAS


def descripcion_conexion() -> str:
    """'host:puerto/base' de la conexión actual, SIN contraseña. Para logs."""
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        return "sin DATABASE_URL"
    base = (urlparse(dsn).path or "").lstrip("/") or "?"
    return f"{_host_puerto(dsn)}/{base}"

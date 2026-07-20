"""Dependencias inyectadas en los routers via FastAPI DI."""

from __future__ import annotations

import os
from typing import Annotated, Generator

from fastapi import Depends, Header, HTTPException

from coop_core.db.connection import DbConnection


def get_db() -> Generator[DbConnection, None, None]:
    """Abre una conexión psycopg3 desde DATABASE_URL y la cierra al terminar el request."""
    import psycopg  # importado aquí para no requerir psycopg en tests con SQLite

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("Variable de entorno DATABASE_URL no configurada.")
    with psycopg.connect(db_url) as conn:
        yield conn  # type: ignore[misc]  # psycopg3 satisface DbConnection Protocol


def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
    token = os.environ.get("API_SECRET_TOKEN", "")
    if not token or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Token ausente o inválido")


DbDep = Annotated[DbConnection, Depends(get_db)]
AuthDep = Annotated[None, Depends(require_auth)]

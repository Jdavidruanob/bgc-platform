import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from coop_api.postgres_schema import CONFIG_DEFAULTS, MIGRATIONS_POSTGRES, SCHEMA_POSTGRES
from coop_api.routers import (
    caja,
    config,
    creditos,
    health,
    notificaciones,
    operaciones,
    recibos_archivos,
    socios,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        import psycopg

        with psycopg.connect(db_url) as conn:
            conn.execute(SCHEMA_POSTGRES)
            for migration in MIGRATIONS_POSTGRES:
                conn.execute(migration)
            for key, value in CONFIG_DEFAULTS.items():
                conn.execute(
                    "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                    (key, value),
                )
            conn.commit()
    yield


app = FastAPI(title="coop-api", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(socios.router)
app.include_router(caja.router)
app.include_router(creditos.router)
app.include_router(operaciones.router)
app.include_router(notificaciones.router)
app.include_router(recibos_archivos.router)
app.include_router(config.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "codigo": "ERROR_INTERNO",
                "mensaje": "Error interno del servidor.",
                "detalle": None,
            }
        },
    )

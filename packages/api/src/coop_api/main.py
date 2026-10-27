import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from coop_api import entorno
from coop_api.arranque import aplicar_esquema
from coop_api.postgres_schema import CONFIG_DEFAULTS, MIGRATIONS_POSTGRES, SCHEMA_POSTGRES
from coop_api.routers import (
    caja,
    config,
    creditos,
    health,
    notificaciones,
    operaciones,
    recibos_archivos,
    recordatorios,
    socios,
    webhook_whatsapp,
)

# Sin esto Python solo muestra WARNING+ y se perdían en producción los INFO
# de la API (entrantes del asistente, estados de entrega de WhatsApp).
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("coop_api").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    db_url = os.environ.get("DATABASE_URL", "")
    logging.getLogger(__name__).warning(
        "coop-api arrancando · entorno=%s · base=%s",
        entorno.get_entorno(),
        entorno.descripcion_conexion(),
    )
    if db_url:
        import psycopg

        with psycopg.connect(db_url, autocommit=True) as conn:
            aplicar_esquema(conn, SCHEMA_POSTGRES, MIGRATIONS_POSTGRES, CONFIG_DEFAULTS)
    yield


app = FastAPI(title="coop-api", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(socios.router)
app.include_router(caja.router)
app.include_router(creditos.router)
app.include_router(operaciones.router)
app.include_router(notificaciones.router)
app.include_router(recordatorios.router)
app.include_router(recibos_archivos.router)
app.include_router(config.router)
app.include_router(webhook_whatsapp.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Excepción no manejada en %s %s", request.method, request.url.path)
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

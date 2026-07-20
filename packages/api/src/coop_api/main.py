from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from coop_api.routers import caja, creditos, health, notificaciones, operaciones, socios


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="coop-api", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(socios.router)
app.include_router(caja.router)
app.include_router(creditos.router)
app.include_router(operaciones.router)
app.include_router(notificaciones.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"codigo": "ERROR_INTERNO", "mensaje": "Error interno del servidor.", "detalle": None}},
    )

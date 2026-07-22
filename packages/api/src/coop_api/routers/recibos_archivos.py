"""Endpoints para consultar los archivos de recibos generados (xlsx + pdf)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from coop_api.deps import AuthDep, DbDep
from coop_api.errors import not_found
from coop_api.recibos.repositorio import RecibosArchivosRepository

router = APIRouter(prefix="/recibos", tags=["recibos"])


@router.get("")
def listar_recibos(
    db: DbDep,
    _auth: AuthDep,
    desde: str | None = Query(default=None, description="ISO 8601, e.g. 2026-01-01"),
    hasta: str | None = Query(default=None, description="ISO 8601, e.g. 2026-12-31"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    repo = RecibosArchivosRepository(db)
    items = repo.listar(desde=desde, hasta=hasta, limit=limit)
    return {"recibos": items}


@router.get("/{recibo_id}/pdf", response_model=None)
def descargar_pdf(recibo_id: int, db: DbDep, _auth: AuthDep) -> Response | JSONResponse:
    repo = RecibosArchivosRepository(db)
    pdf = repo.obtener_pdf(recibo_id)
    if pdf is None:
        return not_found("RECIBO_NO_ENCONTRADO", f"No hay archivo PDF para el recibo {recibo_id}.")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Recibo_{recibo_id}.pdf"'},
    )


@router.get("/{recibo_id}/xlsx", response_model=None)
def descargar_xlsx(recibo_id: int, db: DbDep, _auth: AuthDep) -> Response | JSONResponse:
    repo = RecibosArchivosRepository(db)
    xlsx = repo.obtener_xlsx(recibo_id)
    if xlsx is None:
        return not_found("RECIBO_NO_ENCONTRADO", f"No hay archivo Excel para el recibo {recibo_id}.")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Recibo_{recibo_id}.xlsx"'},
    )

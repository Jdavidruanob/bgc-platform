from coop_contracts.respuestas import (
    CreditoResumen,
    CreditosResponse,
    SocioDetalle,
    SocioSearchItem,
    SociosSearchResponse,
)
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.socios_repo import SociosRepository
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from coop_api.deps import AuthDep, DbDep
from coop_api.errors import not_found
from coop_api.fuzzy import buscar_socios

router = APIRouter(prefix="/socios", tags=["socios"])


@router.get("/lista", response_model=None)
def listar_todos(db: DbDep, _auth: AuthDep) -> SociosSearchResponse:
    """Todos los socios ordenados por nombre. Para que el operador consulte la
    lista completa cuando no recuerda un nombre exacto."""
    socios_repo = SociosRepository(db)
    todos = socios_repo.find_all_full()
    items = [
        SocioSearchItem(
            id=int(str(s["id"])),
            nombres=str(s["nombres"]),
            apellidos=str(s["apellidos"]),
            nombre_completo=f"{s['nombres']} {s['apellidos']}",
            score=1.0,
        )
        for s in todos
    ]
    return SociosSearchResponse(socios=items)


@router.get("", response_model=None)
def buscar(
    db: DbDep,
    _auth: AuthDep,
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
) -> SociosSearchResponse | JSONResponse:
    if not q.strip():
        from coop_api.errors import bad_request

        return bad_request("El parámetro 'q' es requerido y no puede estar vacío.")
    socios_repo = SociosRepository(db)
    todos = socios_repo.find_all_full()
    resultados = buscar_socios(todos, q, limit=limit)
    items = [
        SocioSearchItem(
            id=int(str(s["id"])),
            nombres=str(s["nombres"]),
            apellidos=str(s["apellidos"]),
            nombre_completo=f"{s['nombres']} {s['apellidos']}",
            score=sc,
        )
        for s, sc in resultados
    ]
    return SociosSearchResponse(socios=items)


@router.get("/{socio_id}", response_model=None)
def get_socio(socio_id: int, db: DbDep, _auth: AuthDep) -> SocioDetalle | JSONResponse:
    socios_repo = SociosRepository(db)
    creditos_repo = CreditosRepository(db)
    socio = socios_repo.find_by_id(socio_id)
    if socio is None:
        return not_found("SOCIO_NO_ENCONTRADO", f"No existe un socio con ID {socio_id}.")
    creditos = creditos_repo.find_active_by_socio_id(socio_id)
    return SocioDetalle(
        id=int(socio["id"]),
        nombres=str(socio["nombres"]),
        apellidos=str(socio["apellidos"]),
        celular=str(socio.get("celular") or ""),
        saldo=int(socio["saldo"]),
        creditos_activos=len(creditos),
    )


@router.get("/{socio_id}/creditos", response_model=None)
def get_creditos(socio_id: int, db: DbDep, _auth: AuthDep) -> CreditosResponse | JSONResponse:
    socios_repo = SociosRepository(db)
    if socios_repo.find_by_id(socio_id) is None:
        return not_found("SOCIO_NO_ENCONTRADO", f"No existe un socio con ID {socio_id}.")
    creditos_repo = CreditosRepository(db)
    rows = creditos_repo.find_active_by_socio_id(socio_id)
    creditos = []
    for r in rows:
        letra_id = int(r["letra"])
        detalle = creditos_repo.find_by_letra(letra_id)
        socios_nombres = str(detalle["socios_nombres"]).split(", ") if detalle else []
        creditos.append(
            CreditoResumen(
                letra_id=letra_id,
                capital_original=int(r["capital"]),
                interes_tasa=float(r["interes"]),
                n_cuotas_total=int(r["no_cuotas"]),
                fecha_inicio=str(detalle["fecha_inicio"]) if detalle else "",
                socios=socios_nombres,
            )
        )
    return CreditosResponse(creditos=creditos)

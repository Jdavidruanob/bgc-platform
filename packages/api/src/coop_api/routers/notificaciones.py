from coop_contracts.respuestas import (
    NotificacionesPendientesResponse,
    NotificacionPendiente,
    PatchNotificacionRequest,
)
from coop_core.repositories.notificaciones_repo import NotificacionesRepository
from fastapi import APIRouter

from coop_api.deps import AuthDep, DbDep

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


@router.get("/pendientes")
def get_pendientes(db: DbDep, _auth: AuthDep) -> NotificacionesPendientesResponse:
    repo = NotificacionesRepository(db)
    rows = repo.find_pending()
    notifs = [
        NotificacionPendiente(
            id=int(r["id"]),
            socio_id=int(r["socio_id"]),
            numero_e164=str(r["numero_e164"]),
            texto=str(r["texto"]),
            fecha_creacion=str(r["created_at"]),
        )
        for r in rows
    ]
    return NotificacionesPendientesResponse(notificaciones=notifs)


@router.patch("/{notif_id}", status_code=200)
def patch_notificacion(
    notif_id: int,
    body: PatchNotificacionRequest,
    db: DbDep,
    _auth: AuthDep,
) -> dict[str, object]:
    repo = NotificacionesRepository(db)
    repo.update_estado(notif_id, body.estado, body.error)
    db.commit()
    return {"id": notif_id, "estado": body.estado}

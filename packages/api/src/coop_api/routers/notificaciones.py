from coop_contracts.respuestas import (
    AccionBorradoresResponse,
    BorradoresResponse,
    BorradorNotificacion,
    DocumentoNotificacionRequest,
    NotificacionesPendientesResponse,
    NotificacionPendiente,
    PatchNotificacionRequest,
)
from coop_core.repositories.notificaciones_repo import NotificacionesRepository
from fastapi import APIRouter

from coop_api.deps import AuthDep, DbDep

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


def _nombre(r: dict[str, object]) -> str:
    return f"{r.get('nombres') or ''} {r.get('apellidos') or ''}".strip()


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
            socio_nombre=f"{r.get('nombres') or ''} {r.get('apellidos') or ''}".strip(),
            detalle=str(r["detalle"]) if r.get("detalle") else None,
            documento_tipo=str(r["documento_tipo"]) if r.get("documento_tipo") else None,
            documento_id=int(r["documento_id"]) if r.get("documento_id") is not None else None,
        )
        for r in rows
    ]
    return NotificacionesPendientesResponse(notificaciones=notifs)


@router.get("/borradores/{documento_tipo}/{documento_id}")
def get_borradores(documento_tipo: str, documento_id: int, db: DbDep, _auth: AuthDep) -> BorradoresResponse:
    """Borradores (sin enviar) de un documento, para preguntarle al admin si
    los manda al socio."""
    repo = NotificacionesRepository(db)
    rows = repo.find_borradores_por_documento(documento_tipo, documento_id)
    return BorradoresResponse(
        borradores=[
            BorradorNotificacion(id=int(r["id"]), socio_id=int(r["socio_id"]), socio_nombre=_nombre(r))
            for r in rows
        ]
    )


@router.post("/aprobar")
def aprobar_borradores(
    body: DocumentoNotificacionRequest, db: DbDep, _auth: AuthDep
) -> AccionBorradoresResponse:
    """El admin confirmó: pasa los borradores a 'pendiente' para que se envíen."""
    repo = NotificacionesRepository(db)
    socios = [_nombre(r) for r in repo.find_borradores_por_documento(body.documento_tipo, body.documento_id)]
    repo.aprobar_por_documento(body.documento_tipo, body.documento_id)
    db.commit()
    return AccionBorradoresResponse(afectados=len(socios), socios=socios)


@router.post("/descartar")
def descartar_borradores(
    body: DocumentoNotificacionRequest, db: DbDep, _auth: AuthDep
) -> AccionBorradoresResponse:
    """El admin dijo que no: descarta los borradores (no se envían)."""
    repo = NotificacionesRepository(db)
    socios = [_nombre(r) for r in repo.find_borradores_por_documento(body.documento_tipo, body.documento_id)]
    repo.descartar_por_documento(body.documento_tipo, body.documento_id)
    db.commit()
    return AccionBorradoresResponse(afectados=len(socios), socios=socios)


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

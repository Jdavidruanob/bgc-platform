"""Tests del flujo de borradores del repo de notificaciones WhatsApp."""

from typing import Any

from coop_core.repositories.notificaciones_repo import NotificacionesRepository


def _socio(repos: dict[str, Any], nombres: str = "Ana", apellidos: str = "Perez") -> int:
    return repos["socios"].save(nombres, apellidos, None, None, 0)


def _crear_borrador(repos: dict[str, Any], sid: int, documento_id: int = 5) -> NotificacionesRepository:
    repo = NotificacionesRepository(repos["conn"])
    repo.create(sid, "+573001112233", "hola", "recibo", documento_id, "detalle", estado="borrador")
    repos["conn"].commit()
    return repo


def test_borrador_no_aparece_en_pending(repos: dict[str, Any]) -> None:
    sid = _socio(repos)
    repo = _crear_borrador(repos, sid)
    # Un borrador no lo recoge el procesador (find_pending), pero sí se lista por documento.
    assert repo.find_pending() == []
    borradores = repo.find_borradores_por_documento("recibo", 5)
    assert len(borradores) == 1
    assert borradores[0]["socio_id"] == sid


def test_aprobar_pasa_el_borrador_a_pending(repos: dict[str, Any]) -> None:
    sid = _socio(repos)
    repo = _crear_borrador(repos, sid)
    repo.aprobar_por_documento("recibo", 5)
    repos["conn"].commit()
    assert len(repo.find_pending()) == 1
    assert repo.find_borradores_por_documento("recibo", 5) == []


def test_descartar_no_envia_el_borrador(repos: dict[str, Any]) -> None:
    sid = _socio(repos)
    repo = _crear_borrador(repos, sid)
    repo.descartar_por_documento("recibo", 5)
    repos["conn"].commit()
    assert repo.find_pending() == []
    assert repo.find_borradores_por_documento("recibo", 5) == []


def test_aprobar_solo_afecta_al_documento_indicado(repos: dict[str, Any]) -> None:
    sid = _socio(repos)
    repo = _crear_borrador(repos, sid, documento_id=5)
    repo.create(sid, "+573001112233", "otro", "recibo", 9, "detalle", estado="borrador")
    repos["conn"].commit()
    repo.aprobar_por_documento("recibo", 5)
    repos["conn"].commit()
    # El del documento 9 sigue como borrador (no se tocó).
    assert len(repo.find_borradores_por_documento("recibo", 9)) == 1
    assert repo.find_borradores_por_documento("recibo", 5) == []

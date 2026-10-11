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


# ── Estado de entrega real en WhatsApp ───────────────────────────────────────


def _enviada(repos: dict[str, Any], wamid: str | None = "wamid.A", documento_id: int = 5) -> tuple[Any, int]:
    sid = _socio(repos)
    repo = NotificacionesRepository(repos["conn"])
    nid = repo.create(sid, "+573001112233", "hola", "recordatorio_cuota", documento_id, "{}")
    repo.update_estado(nid, "enviada", None, wamid)
    repos["conn"].commit()
    return repo, nid


def _entrega(repos: dict[str, Any], wamid: str = "wamid.A") -> tuple[Any, Any]:
    fila = (
        repos["conn"]
        .cursor()
        .execute(
            "SELECT entrega_estado, entrega_error FROM notificaciones_whatsapp WHERE wamid = %s", (wamid,)
        )
        .fetchone()
    )
    return fila[0], fila[1]


def test_registrar_entrega_delivered(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    assert repo.registrar_entrega("wamid.A", "delivered") is True
    assert _entrega(repos) == ("delivered", None)


def test_registrar_entrega_wamid_desconocido_devuelve_false(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    assert repo.registrar_entrega("wamid.NO", "delivered") is False


def test_read_se_guarda_como_delivered(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    repo.registrar_entrega("wamid.A", "read")
    assert _entrega(repos)[0] == "delivered"


def test_failed_guarda_el_error(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    repo.registrar_entrega("wamid.A", "failed", "131042: Business eligibility payment issue")
    assert _entrega(repos) == ("failed", "131042: Business eligibility payment issue")


def test_sent_no_degrada_un_delivered(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    repo.registrar_entrega("wamid.A", "delivered")
    repo.registrar_entrega("wamid.A", "sent")  # llega tarde, en desorden
    assert _entrega(repos)[0] == "delivered"


def test_failed_gana_aunque_llegue_delivered_despues(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    repo.registrar_entrega("wamid.A", "failed", "131049: x")
    repo.registrar_entrega("wamid.A", "delivered")
    assert _entrega(repos) == ("failed", "131049: x")


def test_failed_repetido_no_pisa_el_primer_error(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    repo.registrar_entrega("wamid.A", "failed", "131042: pago")
    repo.registrar_entrega("wamid.A", "failed", "otro")  # reintento del webhook
    assert _entrega(repos)[1] == "131042: pago"


def test_entregas_por_avisar_incluye_delivered_y_failed(repos: dict[str, Any]) -> None:
    repo, nid = _enviada(repos)
    repo.registrar_entrega("wamid.A", "delivered")
    repos["conn"].commit()
    filas = repo.find_entregas_por_avisar(30)
    assert [(f["id"], f["resultado"]) for f in filas] == [(nid, "delivered")]


def test_entregas_por_avisar_no_incluye_sent_reciente(repos: dict[str, Any]) -> None:
    repo, _ = _enviada(repos)
    repo.registrar_entrega("wamid.A", "sent")
    repos["conn"].commit()
    assert repo.find_entregas_por_avisar(30) == []


def test_sin_confirmacion_pasados_los_minutos(repos: dict[str, Any]) -> None:
    repo, nid = _enviada(repos)
    repos["conn"].cursor().execute(
        "UPDATE notificaciones_whatsapp SET ultimo_intento_at = %s WHERE id = %s",
        ("2000-01-01 00:00:00", nid),
    )
    repos["conn"].commit()
    filas = repo.find_entregas_por_avisar(30)
    assert [(f["id"], f["resultado"]) for f in filas] == [(nid, "sin_confirmacion")]


def test_sin_wamid_no_se_considera(repos: dict[str, Any]) -> None:
    """Un envío por wa.me (sin Meta) no tiene wamid: nunca espera confirmación."""
    repo, nid = _enviada(repos, wamid=None)
    repos["conn"].cursor().execute(
        "UPDATE notificaciones_whatsapp SET ultimo_intento_at = %s WHERE id = %s",
        ("2000-01-01 00:00:00", nid),
    )
    repos["conn"].commit()
    assert repo.find_entregas_por_avisar(30) == []


def test_marcar_avisadas_no_vuelve_a_listar(repos: dict[str, Any]) -> None:
    repo, nid = _enviada(repos)
    repo.registrar_entrega("wamid.A", "delivered")
    repo.marcar_entregas_avisadas([nid])
    repos["conn"].commit()
    assert repo.find_entregas_por_avisar(30) == []

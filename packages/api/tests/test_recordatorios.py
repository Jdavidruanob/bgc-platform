"""Recordatorios de WhatsApp de mora próxima (ver ADR-010): la cuota vence
hoy y avisa que entrará en mora dentro de los días de gracia."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-secret"}


def _crear_credito_con_cuota(db_conn, fecha_vencimiento: date, whatsapp: str | None = "+573001234567") -> int:
    from coop_core.repositories.creditos_repo import CreditosRepository
    from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
    from coop_core.repositories.socios_repo import SociosRepository

    celular = "3001234567" if whatsapp else None
    sid = SociosRepository(db_conn).save(
        "Pedro Antonio", "Gómez Ruiz", celular, None, saldo=0, whatsapp_e164=whatsapp
    )
    letra_id = CreditosRepository(db_conn).create([sid], 1_200_000, 0.02, 1, "2025-01-01")
    LiquidacionesRepository(db_conn).save_all(
        [(letra_id, 1, fecha_vencimiento.strftime("%Y-%m-%d"), 100_000, 2_000, 102_000, 0)]
    )
    db_conn.commit()
    return letra_id


def test_encola_recordatorio_para_cuota_que_vence_hoy(client: TestClient, db_conn):
    letra_id = _crear_credito_con_cuota(db_conn, date.today())

    r = client.post("/recordatorios/cuotas-proximas", headers=AUTH)

    assert r.status_code == 200
    assert r.json() == {"encoladas": 1}

    pendientes = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    assert len(pendientes) == 1
    assert pendientes[0]["documento_tipo"] == "recordatorio_cuota"
    assert f"letra #{letra_id}" in pendientes[0]["texto"]
    assert "cuota #1" in pendientes[0]["texto"]
    assert "entrará en mora dentro de 5 días" in pendientes[0]["texto"]


def test_encola_barrido_inicial_para_cuota_vencida_hace_pocos_dias(client: TestClient, db_conn):
    """Aún dentro de los días de gracia: todavía se puede avisar."""
    _crear_credito_con_cuota(db_conn, date.today() - timedelta(days=3))

    r = client.post("/recordatorios/cuotas-proximas", headers=AUTH)

    assert r.json() == {"encoladas": 1}


def test_no_avisa_cuotas_futuras(client: TestClient, db_conn):
    _crear_credito_con_cuota(db_conn, date.today() + timedelta(days=1))

    r = client.post("/recordatorios/cuotas-proximas", headers=AUTH)

    assert r.json() == {"encoladas": 0}
    assert client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"] == []


def test_no_avisa_cuotas_que_ya_entraron_en_mora(client: TestClient, db_conn):
    _crear_credito_con_cuota(db_conn, date.today() - timedelta(days=5))

    r = client.post("/recordatorios/cuotas-proximas", headers=AUTH)

    assert r.json() == {"encoladas": 0}
    assert client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"] == []


def test_no_duplica_el_aviso_en_una_segunda_corrida(client: TestClient, db_conn):
    _crear_credito_con_cuota(db_conn, date.today())

    client.post("/recordatorios/cuotas-proximas", headers=AUTH)
    r2 = client.post("/recordatorios/cuotas-proximas", headers=AUTH)

    assert r2.json() == {"encoladas": 0}
    assert len(client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]) == 1


def test_socio_sin_whatsapp_no_genera_notificacion_pero_igual_se_marca(client: TestClient, db_conn):
    _crear_credito_con_cuota(db_conn, date.today(), whatsapp=None)

    r1 = client.post("/recordatorios/cuotas-proximas", headers=AUTH)
    r2 = client.post("/recordatorios/cuotas-proximas", headers=AUTH)

    assert r1.json() == {"encoladas": 0}
    assert r2.json() == {"encoladas": 0}  # no reintenta la misma cuota al día siguiente

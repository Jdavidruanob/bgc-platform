"""Tests de integración de coop-api con SQLite en memoria."""

import uuid

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-secret"}


def _idem() -> dict:
    return {**AUTH, "Idempotency-Key": str(uuid.uuid4())}


# ── Fixtures de datos ─────────────────────────────────────────────────────────


@pytest.fixture()
def socio_pedro(db_conn) -> int:
    from coop_core.repositories.socios_repo import SociosRepository

    repo = SociosRepository(db_conn)
    sid = repo.save(
        "Pedro Antonio",
        "Gómez Ruiz",
        "3001234567",
        None,
        saldo=320000,
        whatsapp_e164="+573001234567",
    )
    db_conn.commit()
    return sid


@pytest.fixture()
def socio_maria(db_conn) -> int:
    from coop_core.repositories.socios_repo import SociosRepository

    repo = SociosRepository(db_conn)
    sid = repo.save("María", "López Herrera", "3112223344", None, saldo=250000, whatsapp_e164="+573112223344")
    db_conn.commit()
    return sid


@pytest.fixture()
def credito_pedro(db_conn, socio_pedro) -> int:
    from datetime import date

    from coop_core.repositories.creditos_repo import CreditosRepository
    from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
    from coop_core.services.amortization import build_amortization_schedule

    creditos_repo = CreditosRepository(db_conn)
    liq_repo = LiquidacionesRepository(db_conn)
    fecha = date(2025, 1, 1)
    letra_id = creditos_repo.create([socio_pedro], 1200000, 0.02, 12, str(fecha))
    cuotas = build_amortization_schedule(letra_id, 1200000, 0.02, 12, fecha)
    liq_repo.save_all(cuotas)
    db_conn.commit()
    return letra_id


# ── Health ────────────────────────────────────────────────────────────────────


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_endpoints_requieren_auth(client: TestClient, socio_pedro):
    r = client.get(f"/socios/{socio_pedro}")
    assert r.status_code == 401


# ── Socios ────────────────────────────────────────────────────────────────────


def test_buscar_socios(client: TestClient, socio_pedro, db_conn):
    from coop_core.repositories.socios_repo import SociosRepository

    repo = SociosRepository(db_conn)
    repo.save("Pedro Luis", "Gómez Castro", None, None, saldo=0)
    db_conn.commit()

    r = client.get("/socios?q=pedro", headers=AUTH)
    assert r.status_code == 200
    socios = r.json()["socios"]
    assert len(socios) >= 2
    nombres = [s["nombres"] for s in socios]
    assert "Pedro Antonio" in nombres
    assert "Pedro Luis" in nombres


def test_buscar_socios_sin_q(client: TestClient):
    r = client.get("/socios?q=", headers=AUTH)
    assert r.status_code == 400


def test_get_socio_existente(client: TestClient, socio_pedro):
    r = client.get(f"/socios/{socio_pedro}", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == socio_pedro
    assert data["saldo"] == 320000


def test_get_socio_inexistente(client: TestClient):
    r = client.get("/socios/9999", headers=AUTH)
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "SOCIO_NO_ENCONTRADO"


def test_get_creditos_socio(client: TestClient, credito_pedro, socio_pedro):
    r = client.get(f"/socios/{socio_pedro}/creditos", headers=AUTH)
    assert r.status_code == 200
    creditos = r.json()["creditos"]
    assert len(creditos) == 1
    assert creditos[0]["letra_id"] == credito_pedro


# ── Caja ──────────────────────────────────────────────────────────────────────


def test_get_caja(client: TestClient):
    r = client.get("/caja", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "saldo_en_caja" in data
    assert data["porcentaje_mora"] == 0.02


# ── Créditos / cuotas ─────────────────────────────────────────────────────────


def test_get_cuotas_pendientes(client: TestClient, credito_pedro):
    r = client.get(f"/creditos/{credito_pedro}/cuotas-pendientes", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["letra_id"] == credito_pedro
    assert len(data["cuotas_pendientes"]) == 12


def test_get_cuotas_letra_inexistente(client: TestClient):
    r = client.get("/creditos/9999/cuotas-pendientes", headers=AUTH)
    assert r.status_code == 404


# ── POST /operaciones/aportes ─────────────────────────────────────────────────


def test_aporte_simple(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 80000}]},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["recibo_id"] is not None
    assert data["aportes"][0]["saldo_nuevo"] == 320000 + 80000


def test_aporte_sin_idempotency_key(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 80000}]},
        headers=AUTH,
    )
    assert r.status_code == 400


def test_aporte_idempotencia(client: TestClient, socio_pedro):
    headers = _idem()
    body = {"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 80000}]}
    r1 = client.post("/operaciones/aportes", json=body, headers=headers)
    r2 = client.post("/operaciones/aportes", json=body, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["recibo_id"] == r2.json()["recibo_id"]
    # El saldo no debe haberse duplicado
    r_socio = client.get(f"/socios/{socio_pedro}", headers=AUTH)
    assert r_socio.json()["saldo"] == 320000 + 80000


def test_aporte_idempotencia_payload_diferente_409(client: TestClient, socio_pedro):
    key = str(uuid.uuid4())
    headers = {**AUTH, "Idempotency-Key": key}
    client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 80000}]},
        headers=headers,
    )
    r2 = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 90000}]},
        headers=headers,
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["codigo"] == "IDEMPOTENCY_CONFLICT"


def test_aporte_socio_inexistente(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": 9999, "aportes": [{"socio_id": socio_pedro, "monto": 80000}]},
        headers=_idem(),
    )
    assert r.status_code == 404


# ── POST /operaciones/retiros ─────────────────────────────────────────────────


def test_retiro_valido(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/retiros",
        json={"socio_id": socio_pedro, "monto": 100000},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["saldo_nuevo"] == 320000 - 100000
    assert data["monto_retirado"] == 100000


def test_retiro_saldo_insuficiente(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/retiros",
        json={"socio_id": socio_pedro, "monto": 999999999},
        headers=_idem(),
    )
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "SALDO_INSUFICIENTE"


# ── POST /operaciones/pagos ───────────────────────────────────────────────────


def test_pago_una_cuota(client: TestClient, socio_pedro, credito_pedro):
    r = client.post(
        "/operaciones/pagos",
        json={
            "recibi_de_id": socio_pedro,
            "pagos": [
                {
                    "socio_id": socio_pedro,
                    "letra_id": credito_pedro,
                    "n_cuotas": 1,
                    "abono_capital": 0,
                }
            ],
        },
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    pago = data["pagos"][0]
    assert pago["cuotas_pagadas"] == [1]
    assert pago["capital_pagado"] > 0


def test_pago_letra_inexistente(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/pagos",
        json={
            "recibi_de_id": socio_pedro,
            "pagos": [{"socio_id": socio_pedro, "letra_id": 9999, "n_cuotas": 1, "abono_capital": 0}],
        },
        headers=_idem(),
    )
    assert r.status_code == 404


def test_pago_cuotas_insuficientes(client: TestClient, socio_pedro, credito_pedro):
    r = client.post(
        "/operaciones/pagos",
        json={
            "recibi_de_id": socio_pedro,
            "pagos": [
                {
                    "socio_id": socio_pedro,
                    "letra_id": credito_pedro,
                    "n_cuotas": 99,
                    "abono_capital": 0,
                }
            ],
        },
        headers=_idem(),
    )
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "CUOTAS_INSUFICIENTES"


# ── POST /operaciones/combinados ──────────────────────────────────────────────


def test_combinado(client: TestClient, socio_pedro, socio_maria, credito_pedro):
    r = client.post(
        "/operaciones/combinados",
        json={
            "recibi_de_id": socio_pedro,
            "aportes": [{"socio_id": socio_maria, "monto": 80000}],
            "pagos": [
                {
                    "socio_id": socio_pedro,
                    "letra_id": credito_pedro,
                    "n_cuotas": 1,
                    "abono_capital": 0,
                }
            ],
        },
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert len(data["aportes"]) == 1
    assert len(data["pagos"]) == 1


# ── Crear crédito ─────────────────────────────────────────────────────────────


def test_crear_credito_genera_tabla_amortizacion(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/creditos",
        json={"socio_ids": [socio_pedro], "capital": 1200000, "n_cuotas": 12},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["letra_id"] is not None
    assert data["interes"] == 0.01  # default del BGC-software
    assert data["n_cuotas"] == 12
    assert len(data["tabla_amortizacion"]) == 12
    # La primera cuota tiene interés sobre el capital completo
    primera = data["tabla_amortizacion"][0]
    assert primera["nro_cuota"] == 1
    assert primera["interes_mes"] == round(1200000 * 0.01)


def test_crear_credito_respeta_interes_explicito(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/creditos",
        json={"socio_ids": [socio_pedro], "capital": 600000, "n_cuotas": 6, "interes": 0.02},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["interes"] == 0.02
    assert data["tabla_amortizacion"][0]["interes_mes"] == round(600000 * 0.02)


def test_crear_credito_capital_invalido(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/creditos",
        json={"socio_ids": [socio_pedro], "capital": 0, "n_cuotas": 6},
        headers=_idem(),
    )
    assert r.status_code == 422  # pydantic gt=0


def test_crear_credito_sin_idempotency_key(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/creditos",
        json={"socio_ids": [socio_pedro], "capital": 600000, "n_cuotas": 6},
        headers=AUTH,
    )
    assert r.status_code == 400


# ── Notificaciones ────────────────────────────────────────────────────────────


def test_notificaciones_pendientes_vacias(client: TestClient):
    r = client.get("/notificaciones/pendientes", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["notificaciones"] == []


def test_crear_y_listar_notificacion(client: TestClient, socio_pedro, db_conn):
    from coop_core.repositories.notificaciones_repo import NotificacionesRepository

    repo = NotificacionesRepository(db_conn)
    repo.create(socio_pedro, "+573001234567", "Hola Pedro, su aporte fue registrado.")
    db_conn.commit()

    r = client.get("/notificaciones/pendientes", headers=AUTH)
    assert r.status_code == 200
    notifs = r.json()["notificaciones"]
    assert len(notifs) == 1
    assert notifs[0]["numero_e164"] == "+573001234567"


def test_patch_notificacion(client: TestClient, socio_pedro, db_conn):
    from coop_core.repositories.notificaciones_repo import NotificacionesRepository

    repo = NotificacionesRepository(db_conn)
    notif_id = repo.create(socio_pedro, "+573001234567", "Texto")
    db_conn.commit()

    r = client.patch(f"/notificaciones/{notif_id}", json={"estado": "enviada"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["estado"] == "enviada"

    # Ya no aparece en pendientes
    r2 = client.get("/notificaciones/pendientes", headers=AUTH)
    assert r2.json()["notificaciones"] == []


# ── Fuzzy search unitario ─────────────────────────────────────────────────────


def test_fuzzy_score():
    from coop_api.fuzzy import score_nombre

    assert score_nombre("pedro", "Pedro Antonio", "Gómez Ruiz") >= 0.7
    assert score_nombre("Maria Lopez", "María", "López Herrera") >= 0.6
    assert score_nombre("xyz_no_existe", "Pedro", "Gómez") < 0.5


def test_fuzzy_prioriza_nombre_sobre_apellido():
    """Regresión: en la cooperativa hay muchos apellidos repetidos por parentesco.
    "Maritza Padilla" debe puntuar más alto contra Maritza que contra otros Padilla.
    """
    from coop_api.fuzzy import score_nombre

    score_maritza = score_nombre("Maritza Padilla", "Maritza Del S.", "Padilla Jojoa")
    score_fanny = score_nombre("Maritza Padilla", "Fanny Patricia", "Padilla Jojoa")
    score_francisco = score_nombre("Maritza Padilla", "Francisco Wilson", "Padilla Jojoa")

    assert score_maritza > score_fanny
    assert score_maritza > score_francisco
    assert score_maritza - score_fanny >= 0.15  # brecha suficiente para auto-pick


def test_fuzzy_tolerante_a_tildes_y_espacios_de_whisper():
    """Whisper suele meter tildes de más y espacios raros. La búsqueda debe ser
    tolerante a esas variaciones."""
    from coop_api.fuzzy import score_nombre

    # Con y sin tilde
    assert score_nombre("Jose David Ruano", "Jose David", "Ruano Burbano") >= 0.85
    assert score_nombre("José David Ruano", "Jose David", "Ruano Burbano") >= 0.85

    # Query mayúsculas / minúsculas
    assert score_nombre("PEDRO GOMEZ", "pedro", "gómez") >= 0.7

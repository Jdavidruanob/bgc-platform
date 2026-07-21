"""Tests de integración del mock server usando TestClient de FastAPI."""

import uuid

import pytest
from coop_contracts.mock_server import app
from fastapi.testclient import TestClient

client = TestClient(app)
AUTH = {"Authorization": "Bearer mock-secret"}


def _idem() -> dict:
    return {**AUTH, "Idempotency-Key": str(uuid.uuid4())}


@pytest.fixture(autouse=True)
def reset():
    client.post("/test/reset")
    yield
    client.post("/test/reset")


# ── Health ────────────────────────────────────────────────────────────────────


def test_health_sin_auth():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_endpoints_requieren_auth():
    r = client.get("/socios?q=pedro")
    assert r.status_code == 401


# ── Socios ────────────────────────────────────────────────────────────────────


def test_buscar_socios_pedro_devuelve_dos_homonimos():
    r = client.get("/socios?q=pedro", headers=AUTH)
    assert r.status_code == 200
    socios = r.json()["socios"]
    ids = [s["id"] for s in socios]
    assert 1 in ids
    assert 2 in ids


def test_buscar_socios_sin_q_retorna_400():
    r = client.get("/socios?q=", headers=AUTH)
    assert r.status_code == 400


def test_get_socio_existente():
    r = client.get("/socios/1", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == 1
    assert "Pedro" in data["nombres"]


def test_get_socio_inexistente_retorna_404():
    r = client.get("/socios/999", headers=AUTH)
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["codigo"] == "SOCIO_NO_ENCONTRADO"


def test_get_creditos_socio():
    r = client.get("/socios/1/creditos", headers=AUTH)
    assert r.status_code == 200
    creditos = r.json()["creditos"]
    assert len(creditos) == 1
    assert creditos[0]["letra_id"] == 450


def test_get_cuotas_pendientes():
    r = client.get("/creditos/450/cuotas-pendientes", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["letra_id"] == 450
    assert len(data["cuotas_pendientes"]) == 2


def test_get_cuotas_letra_inexistente():
    r = client.get("/creditos/999/cuotas-pendientes", headers=AUTH)
    assert r.status_code == 404


# ── Caja ──────────────────────────────────────────────────────────────────────


def test_get_caja():
    r = client.get("/caja", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["saldo_en_caja"] > 0
    assert data["porcentaje_mora"] == 0.02


# ── Aportes ───────────────────────────────────────────────────────────────────


def test_registrar_aporte_simple():
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 80000}]},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["recibo_id"] >= 100
    assert data["aportes"][0]["saldo_nuevo"] == 320000 + 80000


def test_registrar_aporte_socio_inexistente():
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": 999, "aportes": [{"socio_id": 1, "monto": 80000}]},
        headers=_idem(),
    )
    assert r.status_code == 404


def test_registrar_aporte_sin_idempotency_key():
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 80000}]},
        headers=AUTH,
    )
    assert r.status_code == 400


def test_idempotencia_mismo_payload():
    headers = _idem()
    body = {"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 80000}]}
    r1 = client.post("/operaciones/aportes", json=body, headers=headers)
    r2 = client.post("/operaciones/aportes", json=body, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["recibo_id"] == r2.json()["recibo_id"]
    # El saldo no debe haberse incrementado dos veces
    r_socio = client.get("/socios/1", headers=AUTH)
    assert r_socio.json()["saldo"] == 320000 + 80000


def test_idempotencia_payload_diferente_retorna_409():
    key = str(uuid.uuid4())
    headers = {**AUTH, "Idempotency-Key": key}
    client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 80000}]},
        headers=headers,
    )
    r2 = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 90000}]},
        headers=headers,
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["error"]["codigo"] == "IDEMPOTENCY_CONFLICT"


# ── Retiros ───────────────────────────────────────────────────────────────────


def test_registrar_retiro_valido():
    r = client.post(
        "/operaciones/retiros",
        json={"socio_id": 1, "monto": 100000},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["saldo_nuevo"] == 320000 - 100000


def test_retiro_saldo_insuficiente():
    r = client.post(
        "/operaciones/retiros",
        json={"socio_id": 1, "monto": 999999999},
        headers=_idem(),
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["codigo"] == "SALDO_INSUFICIENTE"


# ── Pagos ─────────────────────────────────────────────────────────────────────


def test_registrar_pago_una_cuota():
    r = client.post(
        "/operaciones/pagos",
        json={
            "recibi_de_id": 1,
            "pagos": [{"socio_id": 1, "letra_id": 450, "n_cuotas": 1, "abono_capital": 0}],
        },
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["pagos"][0]["cuotas_pagadas"] == [5]


def test_pago_letra_inexistente():
    r = client.post(
        "/operaciones/pagos",
        json={
            "recibi_de_id": 1,
            "pagos": [{"socio_id": 1, "letra_id": 999, "n_cuotas": 1, "abono_capital": 0}],
        },
        headers=_idem(),
    )
    assert r.status_code == 404


# ── Combinado ─────────────────────────────────────────────────────────────────


def test_registrar_combinado():
    r = client.post(
        "/operaciones/combinados",
        json={
            "recibi_de_id": 1,
            "aportes": [{"socio_id": 1, "monto": 80000}],
            "pagos": [{"socio_id": 1, "letra_id": 450, "n_cuotas": 1, "abono_capital": 0}],
        },
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert len(data["aportes"]) == 1
    assert len(data["pagos"]) == 1


# ── Notificaciones ────────────────────────────────────────────────────────────


def test_get_notificaciones_pendientes():
    r = client.get("/notificaciones/pendientes", headers=AUTH)
    assert r.status_code == 200
    notifs = r.json()["notificaciones"]
    assert len(notifs) >= 1
    assert notifs[0]["numero_e164"].startswith("+57")


def test_patch_notificacion_enviada():
    r = client.patch(
        "/notificaciones/1",
        json={"estado": "enviada"},
        headers=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "enviada"

    # Ya no debe aparecer en pendientes
    r2 = client.get("/notificaciones/pendientes", headers=AUTH)
    ids = [n["id"] for n in r2.json()["notificaciones"]]
    assert 1 not in ids


def test_patch_notificacion_inexistente():
    r = client.patch("/notificaciones/999", json={"estado": "enviada"}, headers=AUTH)
    assert r.status_code == 404


# ── Notificador protocol ──────────────────────────────────────────────────────


def test_mock_notificador_implementa_protocolo():
    from coop_contracts.notificador import MockNotificador, Notificador

    n = MockNotificador()
    assert isinstance(n, Notificador)
    resultado = n.enviar("+573001234567", "Hola socio")
    assert resultado.exitoso
    assert resultado.canal == "mock"
    assert len(n.enviados) == 1

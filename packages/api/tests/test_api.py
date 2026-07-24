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


def test_get_caja_desglosa_administracion(client: TestClient):
    r = client.get("/caja", headers=AUTH)
    data = r.json()
    # Administración = papelería + mora acumulada
    assert data["administracion_total"] == data["papeleria"] + data["mora_acumulada"]
    # Sin operaciones, la mora acumulada es 0
    assert data["mora_acumulada"] == 0


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


# ── Listado y liquidación actual ──────────────────────────────────────────────


def test_listar_todos_socios(client: TestClient, socio_pedro, socio_maria):
    r = client.get("/socios/lista", headers=AUTH)
    assert r.status_code == 200
    nombres = [s["nombre_completo"] for s in r.json()["socios"]]
    assert "Pedro Antonio Gómez Ruiz" in nombres
    assert "María López Herrera" in nombres


def test_liquidacion_actual_letra_inexistente(client: TestClient):
    r = client.get("/creditos/9999/liquidacion-actual/pdf", headers=AUTH)
    assert r.status_code == 404


def test_get_credito_por_letra_incluye_socios(client: TestClient, credito_pedro, socio_pedro):
    r = client.get(f"/creditos/{credito_pedro}", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["letra_id"] == credito_pedro
    ids = [s["id"] for s in data["socios"]]
    assert socio_pedro in ids


def test_pago_excede_limite_de_seis(client: TestClient, socio_pedro, credito_pedro):
    pagos = [
        {"socio_id": socio_pedro, "letra_id": credito_pedro, "n_cuotas": 1, "abono_capital": 0}
        for _ in range(7)
    ]
    r = client.post(
        "/operaciones/pagos",
        json={"recibi_de_id": socio_pedro, "pagos": pagos},
        headers=_idem(),
    )
    assert r.status_code == 422
    assert "RECIBO_EXCEDE_LIMITE" in r.text


def test_liquidacion_actual_genera_pdf(client: TestClient, credito_pedro):
    import shutil

    if shutil.which("soffice") is None and shutil.which("libreoffice") is None:
        import pytest

        pytest.skip("LibreOffice no disponible en este entorno")
    r = client.get(f"/creditos/{credito_pedro}/liquidacion-actual/pdf", headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


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


def test_get_salario_config(client: TestClient):
    r = client.get("/config/salario", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["salario_guardado"] > 0


def test_pago_salario_descuenta_caja_y_guarda_valor(client: TestClient, socio_pedro, db_conn):
    from coop_core.repositories.config_repo import ConfigRepository

    # El tesorero por defecto es el socio 1; en el test usamos el socio del fixture.
    cfg = ConfigRepository(db_conn)
    cfg.set("tesorero_socio_id", str(socio_pedro))
    cfg.set("saldo_en_caja", "5000000")
    db_conn.commit()

    r = client.post(
        "/operaciones/salario",
        json={"mes": "Junio", "monto": 1500000},
        headers=_idem(),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["mes"] == "Junio"
    assert data["monto"] == 1500000
    assert data["saldo_caja_nuevo"] == 5000000 - 1500000
    # El valor confirmado queda guardado para la próxima
    assert client.get("/config/salario", headers=AUTH).json()["salario_guardado"] == 1500000


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


def test_aporte_encola_notificacion_de_recibo(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 80000}]},
        headers=_idem(),
    )
    assert r.status_code == 201
    recibo_id = r.json()["recibo_id"]

    r2 = client.get("/notificaciones/pendientes", headers=AUTH)
    notifs = r2.json()["notificaciones"]
    assert len(notifs) == 1
    assert notifs[0]["socio_id"] == socio_pedro
    assert notifs[0]["numero_e164"] == "+573001234567"
    assert notifs[0]["documento_tipo"] == "recibo"
    assert notifs[0]["documento_id"] == recibo_id
    assert "80.000" in notifs[0]["texto"]


def test_retiro_encola_notificacion(client: TestClient, socio_pedro):
    r = client.post(
        "/operaciones/retiros",
        json={"socio_id": socio_pedro, "monto": 50000},
        headers=_idem(),
    )
    assert r.status_code == 201
    notifs = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    assert len(notifs) == 1
    assert "retiro" in notifs[0]["texto"].lower()
    assert "50.000" in notifs[0]["texto"]


def test_pago_encola_notificacion(client: TestClient, socio_pedro, credito_pedro):
    r = client.post(
        "/operaciones/pagos",
        json={
            "recibi_de_id": socio_pedro,
            "pagos": [
                {"socio_id": socio_pedro, "letra_id": credito_pedro, "n_cuotas": 1, "abono_capital": 0}
            ],
        },
        headers=_idem(),
    )
    assert r.status_code == 201
    notifs = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    assert len(notifs) == 1
    assert str(credito_pedro) in notifs[0]["texto"]


def test_socio_sin_telefono_no_encola_notificacion(client: TestClient, db_conn):
    from coop_core.repositories.socios_repo import SociosRepository

    repo = SociosRepository(db_conn)
    sid = repo.save("Sin", "Teléfono", None, None, saldo=0)
    db_conn.commit()

    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": sid, "aportes": [{"socio_id": sid, "monto": 10000}]},
        headers=_idem(),
    )
    assert r.status_code == 201
    notifs = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    assert notifs == []


def test_crear_credito_encola_notificacion_con_liquidacion(client: TestClient, socio_pedro):
    """El crédito no genera recibo, pero sí liquidación: el socio la recibe adjunta."""
    r = client.post(
        "/operaciones/creditos",
        json={"socio_ids": [socio_pedro], "capital": 600000, "n_cuotas": 6},
        headers=_idem(),
    )
    assert r.status_code == 201
    letra_id = r.json()["letra_id"]
    notifs = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    assert len(notifs) == 1
    assert notifs[0]["documento_tipo"] == "liquidacion"
    assert notifs[0]["documento_id"] == letra_id
    assert "aprobado" in notifs[0]["texto"].lower()


def test_notificacion_saluda_por_nombre_y_trae_nombre_del_socio(client: TestClient, socio_pedro):
    """El mensaje al socio abre con un saludo por su nombre de pila, y la cola
    expone el nombre completo para poder avisarle al operador quién recibió."""
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 50000}]},
        headers=_idem(),
    )
    assert r.status_code == 201
    notifs = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    assert len(notifs) == 1
    assert notifs[0]["texto"].startswith("Hola Pedro")
    assert "Pedro" in notifs[0]["socio_nombre"]


def test_notificacion_guarda_detalle_en_una_sola_linea(client: TestClient, socio_pedro):
    """`detalle` viaja como variable de la plantilla de Meta, que rechaza
    saltos de línea y tabulaciones."""
    r = client.post(
        "/operaciones/aportes",
        json={"recibi_de_id": socio_pedro, "aportes": [{"socio_id": socio_pedro, "monto": 50000}]},
        headers=_idem(),
    )
    assert r.status_code == 201
    notifs = client.get("/notificaciones/pendientes", headers=AUTH).json()["notificaciones"]
    detalle = notifs[0]["detalle"]

    assert detalle.startswith("Registramos tu aporte de $50.000 y tu nuevo saldo es $")
    assert "\n" not in detalle and "\t" not in detalle
    # El mensaje completo se construye a partir del mismo detalle.
    assert detalle in notifs[0]["texto"]


# ── Fuzzy search unitario ─────────────────────────────────────────────────────


def test_fuzzy_score():
    from coop_api.fuzzy import score_nombre

    assert score_nombre("pedro", "Pedro Antonio", "Gómez Ruiz") >= 0.7
    assert score_nombre("Maria Lopez", "María", "López Herrera") >= 0.6
    assert score_nombre("xyz_no_existe", "Pedro", "Gómez") < 0.5


def test_fuzzy_nombre_distorsionado_rescata_por_apellido():
    """Whisper transcribe 'Magceider' como 'Max Eider'. El apellido (García)
    debe rescatar al socio correcto por encima del resto de García."""
    from coop_api.fuzzy import score_nombre

    ganador = score_nombre("Max Eider García", "Magceider", "García Luna")
    otro = score_nombre("Max Eider García", "Rodrigo", "García Castro")
    assert ganador >= 0.75
    assert ganador - otro >= 0.15


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


def test_fuzzy_brecha_amplia_cuando_solo_el_nombre_distingue():
    """Regresión de casos reales: al dar nombre completo con apellidos comunes,
    el ganador debe sacar >= 0.15 de brecha para que el bot lo auto-seleccione."""
    from coop_api.fuzzy import score_nombre

    # Maritza vs otros Padilla Jojoa
    ganador = score_nombre("Maritza Padilla Jojoa", "Maritza Del S.", "Padilla Jojoa")
    segundo = max(
        score_nombre("Maritza Padilla Jojoa", "Sonnia Mabel", "Padilla Jojoa"),
        score_nombre("Maritza Padilla Jojoa", "Fanny Patricia", "Padilla Jojoa"),
    )
    assert ganador - segundo >= 0.15

    # Marcela Salazar vs otros Salazar
    ganador2 = score_nombre("Marcela Salazar Flores", "Marcela", "Salazar Florez")
    segundo2 = max(
        score_nombre("Marcela Salazar Flores", "Mariana García", "Salazar"),
        score_nombre("Marcela Salazar Flores", "Isabella García", "Salazar"),
    )
    assert ganador2 - segundo2 >= 0.15

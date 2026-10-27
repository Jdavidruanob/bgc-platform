"""Tests del asistente de WhatsApp de socios (ver ADR-011): el webhook, la
identificación por número, el menú de botones y la guarda de privacidad
central (nunca mostrar datos de un crédito que no es del que escribe)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Generator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("WHATSAPP_APP_SECRET", "test-app-secret")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "test-verify-token")

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"

NUM_PEDRO_META = "573001234567"
NUM_PEDRO_E164 = "+573001234567"
NUM_MARIA_META = "573112223344"
NUM_MARIA_E164 = "+573112223344"
NUM_DESCONOCIDO_META = "573009998877"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def cliente_wa() -> Generator[Any, None, None]:
    from coop_api.asistente.whatsapp_cliente import ClienteFalso, get_cliente_whatsapp
    from coop_api.main import app

    falso = ClienteFalso()
    app.dependency_overrides[get_cliente_whatsapp] = lambda: falso
    yield falso
    app.dependency_overrides.pop(get_cliente_whatsapp, None)


@pytest.fixture(autouse=True)
def _numeros_autorizados(monkeypatch: pytest.MonkeyPatch) -> None:
    # Por defecto, en los tests el asistente le responde a cualquier número
    # (equivalente a "*"); el test de lista blanca lo sobreescribe.
    monkeypatch.setenv("WHATSAPP_ASISTENTE_NUMEROS", "*")


@pytest.fixture(autouse=True)
def _limitador_limpio() -> Generator[None, None, None]:
    from coop_api.asistente.limite import limitador

    limitador.reiniciar()
    yield
    limitador.reiniciar()


def _crear_socio(
    db_conn: Any, nombres: str, apellidos: str, celular: str, whatsapp_e164: str, saldo: int = 0
) -> int:
    from coop_core.repositories.socios_repo import SociosRepository

    sid = SociosRepository(db_conn).save(
        nombres, apellidos, celular, None, saldo=saldo, whatsapp_e164=whatsapp_e164
    )
    db_conn.commit()
    return sid


def _crear_credito(db_conn: Any, socio_ids: list[int], n_cuotas: int = 12) -> int:
    from coop_core.repositories.creditos_repo import CreditosRepository
    from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
    from coop_core.services.amortization import build_amortization_schedule

    letra_id = CreditosRepository(db_conn).create(socio_ids, 1_200_000, 0.02, n_cuotas, "2025-01-01")
    cuotas = build_amortization_schedule(letra_id, 1_200_000, 0.02, n_cuotas, date(2025, 1, 1))
    LiquidacionesRepository(db_conn).save_all(cuotas)
    db_conn.commit()
    return letra_id


def _crear_credito_con_cuotas(db_conn: Any, socio_ids: list[int], cuotas: list[tuple[Any, ...]]) -> int:
    from coop_core.repositories.creditos_repo import CreditosRepository
    from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository

    letra_id = CreditosRepository(db_conn).create(socio_ids, 1_200_000, 0.02, len(cuotas), "2025-01-01")
    filas = [(letra_id, *c) for c in cuotas]
    LiquidacionesRepository(db_conn).save_all(filas)
    db_conn.commit()
    return letra_id


# ── Constructores de sobres de Meta ─────────────────────────────────────────


def _sobre(
    mensajes: list[dict[str, Any]] | None = None, statuses: list[dict[str, Any]] | None = None
) -> dict:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "573000000000", "phone_number_id": "pnid123"},
    }
    if mensajes is not None:
        value["messages"] = mensajes
    if statuses is not None:
        value["statuses"] = statuses
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba123", "changes": [{"field": "messages", "value": value}]}],
    }


def _msg_texto(numero: str, texto: str, wamid: str = "wamid.1") -> dict:
    return {"from": numero, "id": wamid, "timestamp": "1700000000", "type": "text", "text": {"body": texto}}


def _msg_boton(numero: str, boton_id: str, wamid: str = "wamid.2") -> dict:
    return {
        "from": numero,
        "id": wamid,
        "timestamp": "1700000000",
        "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": boton_id, "title": "x"}},
    }


def _msg_audio(numero: str, wamid: str = "wamid.3") -> dict:
    return {
        "from": numero,
        "id": wamid,
        "timestamp": "1700000000",
        "type": "audio",
        "audio": {"id": "media1", "mime_type": "audio/ogg", "voice": True},
    }


def _firmar(cuerpo: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), cuerpo, hashlib.sha256).hexdigest()


def _post(client: TestClient, payload: dict, *, secret: str | None = APP_SECRET, sin_firma: bool = False):
    cuerpo = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if not sin_firma:
        headers["X-Hub-Signature-256"] = _firmar(cuerpo, secret or APP_SECRET)
    return client.post("/webhooks/whatsapp", content=cuerpo, headers=headers)


# ── Handshake y firma ────────────────────────────────────────────────────────


def test_handshake_token_correcto(client: TestClient) -> None:
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "12345"},
    )
    assert r.status_code == 200
    assert r.text == "12345"


def test_handshake_token_incorrecto(client: TestClient) -> None:
    r = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "12345"},
    )
    assert r.status_code == 403


def test_post_firma_invalida(client: TestClient, cliente_wa: Any) -> None:
    r = _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola")]), secret="secreto-incorrecto")
    assert r.status_code == 403
    assert cliente_wa.textos == [] and cliente_wa.botones == []


def test_post_sin_firma(client: TestClient, cliente_wa: Any) -> None:
    r = _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola")]), sin_firma=True)
    assert r.status_code == 403


def test_post_cuerpo_no_json(client: TestClient, cliente_wa: Any) -> None:
    cuerpo = b"esto no es json"
    r = client.post(
        "/webhooks/whatsapp",
        content=cuerpo,
        headers={"X-Hub-Signature-256": _firmar(cuerpo), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert cliente_wa.textos == [] and cliente_wa.botones == []


# ── Identidad ────────────────────────────────────────────────────────────────


def test_saludo_socio_conocido(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola")]))
    assert r.status_code == 200
    assert len(cliente_wa.botones) == 1
    numero, texto, botones = cliente_wa.botones[0]
    assert numero == NUM_PEDRO_E164
    assert "Pedro" in texto
    assert [b.id for b in botones] == ["menu:aportes", "menu:creditos", "menu:pagos"]


def test_numero_no_reconocido_no_recibe_respuesta(client: TestClient, cliente_wa: Any) -> None:
    # Contestarle a desconocidos alimentaba un ping-pong con otros bots.
    r = _post(client, _sobre([_msg_texto(NUM_DESCONOCIDO_META, "Hola")]))
    assert r.status_code == 200
    assert cliente_wa.textos == [] and cliente_wa.botones == [] and cliente_wa.documentos == []


def test_entrante_se_registra_con_numero_enmascarado(
    client: TestClient, cliente_wa: Any, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="coop_api.routers.webhook_whatsapp"):
        _post(client, _sobre([_msg_texto(NUM_DESCONOCIDO_META, "Hola", wamid="wamid.log")]))
    textos = [x.getMessage() for x in caplog.records]
    assert any("de=***8877" in t and "tipo=texto" in t and "wamid.log" in t for t in textos)
    assert not any(NUM_DESCONOCIDO_META in t for t in textos)


def test_tope_de_respuestas_por_numero(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    from coop_api.asistente.limite import MAX_RESPUESTAS

    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    for i in range(MAX_RESPUESTAS + 5):
        _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola", wamid=f"wamid.t{i}")]))
    assert len(cliente_wa.botones) == MAX_RESPUESTAS


def test_tope_es_por_numero(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    from coop_api.asistente.limite import MAX_RESPUESTAS

    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    _crear_socio(db_conn, "María", "López", "3112223344", NUM_MARIA_E164)
    for i in range(MAX_RESPUESTAS + 2):
        _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola", wamid=f"wamid.p{i}")]))
    _post(client, _sobre([_msg_texto(NUM_MARIA_META, "Hola", wamid="wamid.m")]))
    assert cliente_wa.botones[-1][0] == NUM_MARIA_E164


def test_reintento_de_meta_con_mismo_wamid_no_responde_dos_veces(
    client: TestClient, db_conn: Any, cliente_wa: Any
) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    sobre = _sobre([_msg_texto(NUM_PEDRO_META, "Hola", wamid="wamid.mismo")])
    _post(client, sobre)
    _post(client, sobre)
    assert len(cliente_wa.botones) == 1


@pytest.mark.parametrize("tipo", ["reaction", "system", "unsupported"])
def test_reacciones_y_avisos_del_sistema_no_se_responden(
    client: TestClient, db_conn: Any, cliente_wa: Any, tipo: str
) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    msg = {"from": NUM_PEDRO_META, "id": f"wamid.{tipo}", "timestamp": "1700000000", "type": tipo}
    _post(client, _sobre([msg]))
    assert cliente_wa.textos == [] and cliente_wa.botones == []


def test_numero_fuera_de_lista_blanca(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHATSAPP_ASISTENTE_NUMEROS", "+573000000000")
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola")]))
    assert r.status_code == 200
    assert cliente_wa.textos == [] and cliente_wa.botones == []


def test_reconocido_por_celular_derivado(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    from coop_core.repositories.socios_repo import SociosRepository

    SociosRepository(db_conn).save("Luisa", "Cardona", "3007778899", None)
    db_conn.commit()
    r = _post(client, _sobre([_msg_texto("573007778899", "Hola")]))
    assert r.status_code == 200
    assert len(cliente_wa.botones) == 1
    assert "Luisa" in cliente_wa.botones[0][1]


# ── Menú: saldo de aportes ────────────────────────────────────────────────────


def test_menu_aportes(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164, saldo=1_250_000)
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "menu:aportes")]))
    assert r.status_code == 200
    _, texto, _ = cliente_wa.botones[0]
    assert "1.250.000" in texto


# ── Menú: mis créditos ────────────────────────────────────────────────────────


def test_menu_creditos_sin_creditos(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "menu:creditos")]))
    assert r.status_code == 200
    _, texto, botones = cliente_wa.botones[0]
    assert "#" not in texto
    assert [b.id for b in botones] == ["fin:otra", "fin:no"]


def test_menu_creditos_uno_activo(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    letra_id = _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "menu:creditos")]))
    assert r.status_code == 200
    _, texto, botones = cliente_wa.botones[0]
    assert f"#{letra_id}" in texto
    assert [b.id for b in botones] == ["liq:si", "liq:no"]


def test_liq_no_gracias(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:no")]))
    assert r.status_code == 200
    assert cliente_wa.documentos == []


def test_liq_si_un_credito_envia_pdf(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("coop_api.asistente.liquidacion.xlsx_a_pdf", lambda _xlsx: b"%PDF-1.4 fake")
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    letra_id = _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:si")]))
    assert r.status_code == 200
    assert len(cliente_wa.documentos) == 1
    numero, documento = cliente_wa.documentos[0]
    assert numero == NUM_PEDRO_E164
    assert documento.contenido == b"%PDF-1.4 fake"
    assert f"letra #{letra_id}" in documento.caption


def test_liq_si_dos_creditos_pide_elegir(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    letra_a = _crear_credito(db_conn, [sid])
    letra_b = _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:si")]))
    assert r.status_code == 200
    assert cliente_wa.documentos == []
    _, _, botones = cliente_wa.botones[0]
    ids = {b.id for b in botones}
    assert ids == {f"liq:letra:{letra_a}", f"liq:letra:{letra_b}", "liq:todos"}


def test_liq_si_tres_creditos_usa_lista(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    for _ in range(3):
        _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:si")]))
    assert r.status_code == 200
    assert len(cliente_wa.listas) == 1
    _, _, _, filas = cliente_wa.listas[0]
    assert len(filas) == 4  # 3 letras + "De todos"


def test_liq_todos_envia_un_pdf_por_credito(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("coop_api.asistente.liquidacion.xlsx_a_pdf", lambda _xlsx: b"%PDF-1.4 fake")
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    _crear_credito(db_conn, [sid])
    _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:todos")]))
    assert r.status_code == 200
    assert len(cliente_wa.documentos) == 2


def test_liq_pdf_no_disponible(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coop_api.recibos.pdf_converter import PdfConversionError

    def _falla(_xlsx: bytes) -> bytes:
        raise PdfConversionError("soffice no disponible")

    monkeypatch.setattr("coop_api.asistente.liquidacion.xlsx_a_pdf", _falla)
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:si")]))
    assert r.status_code == 200
    assert cliente_wa.documentos == []
    assert any("no puedo" in t.lower() or "inténtalo" in t.lower() for _, t in cliente_wa.textos)


# ── Guarda de privacidad central ─────────────────────────────────────────────


def test_liq_letra_ajena_no_se_envia(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    pedro = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    maria = _crear_socio(db_conn, "María", "López Herrera", "3112223344", NUM_MARIA_E164)
    _crear_credito(db_conn, [pedro])
    letra_maria = _crear_credito(db_conn, [maria])

    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, f"liq:letra:{letra_maria}")]))

    assert r.status_code == 200
    assert cliente_wa.documentos == []
    _, texto, botones = cliente_wa.botones[0]
    assert str(letra_maria) not in texto
    assert [b.id for b in botones] == ["menu:aportes", "menu:creditos", "menu:pagos"]


def test_liq_letra_inexistente_no_se_envia(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:letra:99999")]))
    assert r.status_code == 200
    assert cliente_wa.documentos == []


def test_boton_id_basura(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    for basura in ["liq:letra:abc", "hackea:todo", "", "a" * 300]:
        cliente_wa.documentos.clear()
        r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, basura)]))
        assert r.status_code == 200
        assert cliente_wa.documentos == []


# ── Menú: próximos pagos ──────────────────────────────────────────────────────


def test_menu_pagos_sin_creditos(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "menu:pagos")]))
    assert r.status_code == 200
    _, texto, _ = cliente_wa.botones[0]
    assert "no tienes pagos pendientes" in texto.lower()


def test_menu_pagos_con_vencida_y_futura(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    hoy = date.today()
    vencida = hoy - timedelta(days=30)
    futura = hoy + timedelta(days=20)
    letra_id = _crear_credito_con_cuotas(
        db_conn,
        [sid],
        [
            (1, vencida.strftime("%Y-%m-%d"), 100_000, 2_000, 102_000, 0),
            (2, futura.strftime("%Y-%m-%d"), 100_000, 2_000, 102_000, 0),
        ],
    )
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "menu:pagos")]))
    assert r.status_code == 200
    _, texto, _ = cliente_wa.botones[0]
    assert f"Letra #{letra_id}" in texto
    assert "venció" in texto
    assert "mora" in texto
    assert futura.strftime("%d/%m/%Y") in texto


# ── Tipos de mensaje que no son botón ni texto ───────────────────────────────


def test_statuses_se_ignoran(client: TestClient, cliente_wa: Any) -> None:
    r = _post(client, _sobre(statuses=[{"id": "wamid.s1", "status": "delivered"}]))
    assert r.status_code == 200
    assert cliente_wa.textos == [] and cliente_wa.botones == []


def test_status_failed_se_registra_como_warning_con_el_codigo_de_meta(
    client: TestClient, cliente_wa: Any, caplog: pytest.LogCaptureFixture
) -> None:
    status = {
        "id": "wamid.fallido",
        "status": "failed",
        "recipient_id": "573001234567",
        "errors": [{"code": 131049, "title": "Message undeliverable"}],
    }
    with caplog.at_level("INFO", logger="coop_api.routers.webhook_whatsapp"):
        r = _post(client, _sobre(statuses=[status]))

    assert r.status_code == 200
    avisos = [x for x in caplog.records if x.levelname == "WARNING"]
    assert len(avisos) == 1
    mensaje = avisos[0].getMessage()
    assert "wamid.fallido" in mensaje and "131049" in mensaje
    assert "573001234567" not in mensaje  # el número se enmascara


def test_status_delivered_se_registra_como_info(
    client: TestClient, cliente_wa: Any, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="coop_api.routers.webhook_whatsapp"):
        _post(
            client,
            _sobre(statuses=[{"id": "wamid.ok", "status": "delivered", "recipient_id": "573001234567"}]),
        )

    registros = [x for x in caplog.records if "wamid.ok" in x.getMessage()]
    assert registros and {x.levelname for x in registros} == {"INFO"}
    assert any("estado=delivered" in x.getMessage() for x in registros)


def test_nota_de_voz(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_audio(NUM_PEDRO_META)]))
    assert r.status_code == 200
    assert len(cliente_wa.botones) == 1
    _, texto, _ = cliente_wa.botones[0]
    assert "notas de voz" in texto.lower()


def test_excepcion_interna_sigue_devolviendo_200(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)

    def _explota(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("coop_api.routers.webhook_whatsapp.flujo.atender", _explota)
    r = _post(client, _sobre([_msg_texto(NUM_PEDRO_META, "Hola")]))
    assert r.status_code == 200


# ── Seguimiento tras responder y despedida ───────────────────────────────────


def test_respuesta_ofrece_seguir_o_despedirse(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164, saldo=50_000)
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "menu:aportes")]))
    assert r.status_code == 200
    _, texto, botones = cliente_wa.botones[0]
    assert "50.000" in texto
    assert "algo más" in texto.lower()
    assert [b.id for b in botones] == ["fin:otra", "fin:no"]


def test_fin_otra_vuelve_al_menu_principal(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "fin:otra")]))
    assert r.status_code == 200
    _, texto, botones = cliente_wa.botones[0]
    assert "Pedro" in texto
    assert [b.id for b in botones] == ["menu:aportes", "menu:creditos", "menu:pagos"]


def test_fin_no_se_despide_sin_botones(client: TestClient, db_conn: Any, cliente_wa: Any) -> None:
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "fin:no")]))
    assert r.status_code == 200
    assert cliente_wa.botones == []
    assert len(cliente_wa.textos) == 1
    _, texto = cliente_wa.textos[0]
    assert "Pedro" in texto
    assert "servicio" in texto.lower()


def test_liq_si_un_credito_ofrece_seguimiento(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("coop_api.asistente.liquidacion.xlsx_a_pdf", lambda _xlsx: b"%PDF-1.4 fake")
    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    _crear_credito(db_conn, [sid])
    r = _post(client, _sobre([_msg_boton(NUM_PEDRO_META, "liq:si")]))
    assert r.status_code == 200
    assert len(cliente_wa.documentos) == 1
    _, texto, botones = cliente_wa.botones[0]
    assert "preparando" in texto.lower()
    assert [b.id for b in botones] == ["fin:otra", "fin:no"]


# ── El estado de entrega se guarda en la notificación ───────────────────────


def _notificacion_enviada(db_conn: Any, wamid: str) -> int:
    from coop_core.repositories.notificaciones_repo import NotificacionesRepository

    sid = _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    repo = NotificacionesRepository(db_conn)
    nid = repo.create(sid, NUM_PEDRO_E164, "hola", "recordatorio_cuota", 1, "{}")
    repo.update_estado(nid, "enviada", None, wamid)
    db_conn.commit()
    return nid


def _entrega_guardada(db_conn: Any, nid: int) -> tuple[Any, Any]:
    fila = (
        db_conn.cursor()
        .execute("SELECT entrega_estado, entrega_error FROM notificaciones_whatsapp WHERE id = %s", (nid,))
        .fetchone()
    )
    return fila[0], fila[1]


def test_webhook_guarda_delivered_en_la_notificacion(client: TestClient, db_conn: Any) -> None:
    nid = _notificacion_enviada(db_conn, "wamid.E1")
    r = _post(
        client, _sobre(statuses=[{"id": "wamid.E1", "status": "delivered", "recipient_id": NUM_PEDRO_META}])
    )
    assert r.status_code == 200
    assert _entrega_guardada(db_conn, nid) == ("delivered", None)


def test_webhook_guarda_failed_con_el_codigo_de_meta(client: TestClient, db_conn: Any) -> None:
    nid = _notificacion_enviada(db_conn, "wamid.E2")
    estado = {
        "id": "wamid.E2",
        "status": "failed",
        "recipient_id": NUM_PEDRO_META,
        "errors": [{"code": 131042, "title": "Business eligibility payment issue"}],
    }
    _post(client, _sobre(statuses=[estado]))
    assert _entrega_guardada(db_conn, nid) == ("failed", "131042: Business eligibility payment issue")


def test_webhook_con_wamid_desconocido_responde_200(client: TestClient) -> None:
    r = _post(client, _sobre(statuses=[{"id": "wamid.NADA", "status": "delivered"}]))
    assert r.status_code == 200


def test_webhook_sigue_atendiendo_mensajes_aunque_falle_guardar_el_estado(
    client: TestClient, db_conn: Any, cliente_wa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coop_core.repositories.notificaciones_repo import NotificacionesRepository

    def _roto(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("base caída")

    monkeypatch.setattr(NotificacionesRepository, "registrar_entrega", _roto)
    _crear_socio(db_conn, "Pedro Antonio", "Gómez Ruiz", "3001234567", NUM_PEDRO_E164)
    payload = _sobre(
        [_msg_texto(NUM_PEDRO_META, "Hola")], statuses=[{"id": "wamid.X", "status": "delivered"}]
    )
    r = _post(client, payload)
    assert r.status_code == 200
    assert cliente_wa.botones or cliente_wa.textos  # el asistente respondió igual

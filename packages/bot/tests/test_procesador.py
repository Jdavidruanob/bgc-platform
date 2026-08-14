import json

from coop_bot.adaptadores.telegram import _texto_aviso_operador
from coop_bot.api.cliente import ApiClient
from coop_bot.notificaciones.procesador import (
    EnvioRealizado,
    ResumenProcesamiento,
    _procesar_una,
    procesar_pendientes,
)
from coop_contracts.notificador import MockNotificador, ResultadoEnvio
from coop_contracts.respuestas import NotificacionPendiente


class _NotificadorQueFalla:
    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        return ResultadoEnvio(exitoso=False, canal="cloud_api", error="rechazado por Meta")


class _NotificadorQueExplota:
    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        raise RuntimeError("boom")


async def test_procesa_la_notificacion_semilla_del_mock(api_client: ApiClient) -> None:
    notificador = MockNotificador()

    resumen = await procesar_pendientes(api_client, notificador)

    assert resumen.enviadas == 1
    assert resumen.fallidas == 0
    assert len(notificador.enviados) == 1
    assert notificador.enviados[0]["numero_e164"] == "+573112223344"

    pendientes = await api_client.get_notificaciones_pendientes()
    assert pendientes.notificaciones == []


async def test_resumen_registra_a_quien_se_le_envio(api_client: ApiClient) -> None:
    """El operador tiene que poder ver el nombre del socio que ya recibió."""
    resumen = await procesar_pendientes(api_client, MockNotificador())

    assert [e.socio_nombre for e in resumen.envios] == ["María López Herrera"]
    assert resumen.envios[0].entregado is True


async def test_resumen_registra_los_fallos_con_nombre(api_client: ApiClient) -> None:
    resumen = await procesar_pendientes(api_client, _NotificadorQueFalla())

    assert resumen.fallos == [("María López Herrera", "rechazado por Meta")]


# ── Aviso al operador ────────────────────────────────────────────────────────


def test_aviso_operador_lista_los_entregados() -> None:
    resumen = ResumenProcesamiento(envios=[EnvioRealizado(socio_nombre="Pedro Gómez", canal="cloud_api")])

    aviso = _texto_aviso_operador(resumen)

    assert "Ya recibieron su comprobante" in aviso
    assert "Pedro Gómez" in aviso


def test_aviso_operador_separa_el_fallback_wa_me_de_lo_ya_entregado() -> None:
    """Un link wa.me NO es una entrega: el socio todavía no recibió nada."""
    resumen = ResumenProcesamiento(
        envios=[
            EnvioRealizado(
                socio_nombre="Pedro Gómez",
                canal="wa_me_link",
                wa_me_url="https://wa.me/573112223344?text=hola",
            )
        ]
    )

    aviso = _texto_aviso_operador(resumen)

    assert "Ya recibieron su comprobante" not in aviso
    assert "enviar a mano" in aviso
    assert "https://wa.me/573112223344?text=hola" in aviso


def test_aviso_operador_reporta_fallos() -> None:
    resumen = ResumenProcesamiento(fallos=[("Pedro Gómez", "rechazado por Meta")])

    aviso = _texto_aviso_operador(resumen)

    assert "No pude enviarle" in aviso
    assert "rechazado por Meta" in aviso


def test_aviso_operador_vacio_si_no_hubo_nada() -> None:
    assert _texto_aviso_operador(ResumenProcesamiento()) == ""


async def test_sin_pendientes_no_hace_nada(api_client: ApiClient) -> None:
    await procesar_pendientes(api_client, MockNotificador())  # consume la única semilla

    resumen = await procesar_pendientes(api_client, MockNotificador())

    assert resumen.enviadas == 0
    assert resumen.fallidas == 0
    assert resumen.errores == []


async def test_notificacion_fallida_se_marca_como_fallida_y_no_bloquea(
    api_client: ApiClient,
) -> None:
    resumen = await procesar_pendientes(api_client, _NotificadorQueFalla())

    assert resumen.enviadas == 0
    assert resumen.fallidas == 1
    assert "rechazado por Meta" in resumen.errores

    pendientes = await api_client.get_notificaciones_pendientes()
    assert pendientes.notificaciones == []  # ya no está "pendiente", quedó "fallida"


async def test_excepcion_del_notificador_se_captura_y_marca_fallida(
    api_client: ApiClient,
) -> None:
    resumen = await procesar_pendientes(api_client, _NotificadorQueExplota())

    assert resumen.fallidas == 1
    assert any("boom" in error for error in resumen.errores)


# ── Recordatorios de cuota próxima ──────────────────────────────────────────


class _ClienteSinDescargas:
    """Stub de ApiClient: solo implementa lo que necesita `_marcar` (PATCH). Los
    recordatorios no tienen documento adjunto, así que `_procesar_una` nunca
    debería intentar descargar nada a través de este cliente."""

    def __init__(self) -> None:
        self.patches: list[tuple[int, str, str | None]] = []

    async def patch_notificacion(self, notificacion_id: int, estado: str, error: str | None = None) -> None:
        self.patches.append((notificacion_id, estado, error))


def _notificacion_recordatorio() -> NotificacionPendiente:
    return NotificacionPendiente(
        id=42,
        socio_id=7,
        numero_e164="+573112223344",
        texto="Hola, Pedro 👋\n\nTe informamos que la cuota #3 de tu crédito con letra #12 ...",
        fecha_creacion="2026-08-13T00:00:00",
        socio_nombre="Pedro Gómez",
        detalle=json.dumps(
            {
                "numero_cuota": "3",
                "numero_letra": "12",
                "fecha_pago_cuota": "13/08/2026",
                "fecha_mora": "18/08/2026",
                "monto_mora": "$2.000",
            }
        ),
        documento_tipo="recordatorio_cuota",
        documento_id=99,
    )


async def test_recordatorio_de_cuota_usa_enviar_recordatorio_con_los_params() -> None:
    notificador = MockNotificador()
    cliente = _ClienteSinDescargas()
    resumen = ResumenProcesamiento()

    await _procesar_una(cliente, notificador, _notificacion_recordatorio(), resumen)

    assert resumen.enviadas == 1
    assert cliente.patches == [(42, "enviada", None)]
    assert len(notificador.recordatorios_enviados) == 1
    enviado = notificador.recordatorios_enviados[0]
    assert enviado["numero_e164"] == "+573112223344"
    assert enviado["plantilla"] == {
        "nombre": "Pedro",
        "numero_cuota": "3",
        "numero_letra": "12",
        "fecha_pago_cuota": "13/08/2026",
        "fecha_mora": "18/08/2026",
        "monto_mora": "$2.000",
    }
    # No debe pasar por el camino de documento: ni recibo ni liquidación.
    assert notificador.documentos_enviados == []

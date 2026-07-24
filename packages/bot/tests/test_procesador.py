from coop_bot.adaptadores.telegram import _texto_aviso_operador
from coop_bot.api.cliente import ApiClient
from coop_bot.notificaciones.procesador import (
    EnvioRealizado,
    ResumenProcesamiento,
    procesar_pendientes,
)
from coop_contracts.notificador import MockNotificador, ResultadoEnvio


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

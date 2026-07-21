from coop_bot.api.cliente import ApiClient
from coop_bot.notificaciones.procesador import procesar_pendientes
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

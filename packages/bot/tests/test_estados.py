from coop_bot.api.cliente import ApiClient
from coop_bot.dialogo.estados import EstadoDialogo, MaquinaEstados, SesionDialogo
from coop_contracts.intenciones import (
    IntAmbigua,
    IntConsultarCaja,
    IntConsultarCuotas,
    IntConsultarSocio,
    IntCrearCredito,
    IntDesconocida,
    IntIncompleta,
    IntRegRetiro,
)


def _maquina(cliente: ApiClient) -> MaquinaEstados:
    return MaquinaEstados(SesionDialogo(chat_id=1), cliente)


# ── Casos de NLU que no requieren la API ─────────────────────────────────────


async def test_intencion_incompleta_pide_completar(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntIncompleta(
        intencion="incompleta",
        intencion_detectada="registrar_aporte",
        campos_faltantes=["monto"],
        texto_original="le recibí a Pedro",
    )
    respuesta = await maquina.procesar_intencion(intencion)
    assert "monto" in respuesta.texto
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta.requiere_timeout is False


async def test_intencion_desconocida(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntDesconocida(intencion="desconocida", texto_original="asdasd")
    respuesta = await maquina.procesar_intencion(intencion)
    assert "no entendí" in respuesta.texto.lower()
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE


async def test_intencion_ambigua(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntAmbigua(
        intencion="ambigua",
        posibles_intenciones=["registrar_aporte", "registrar_pago"],
        texto_original="le recibí a Pedro doscientos mil",
    )
    respuesta = await maquina.procesar_intencion(intencion)
    assert "registrar_aporte" in respuesta.texto


async def test_crear_credito_es_un_stub(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntCrearCredito(intencion="crear_credito", socios=["Pedro Gómez"], capital=1, n_cuotas=1)
    )
    assert "no está disponible" in respuesta.texto.lower()
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE


# ── Consultas (B-15) ──────────────────────────────────────────────────────────


async def test_consultar_caja(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(IntConsultarCaja(intencion="consultar_caja"))

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "$5.830.000" in respuesta.texto
    assert respuesta.cancelar_timeout is True
    assert maquina.sesion.intencion is None


async def test_consultar_socio(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarSocio(intencion="consultar_socio", socio="Carmenza Suárez Peña")
    )

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Carmenza Suárez Peña" in respuesta.texto
    assert "$180.000" in respuesta.texto
    assert "Créditos activos: 0" in respuesta.texto


async def test_consultar_socio_homonimos_dispara_desambiguacion(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarSocio(intencion="consultar_socio", socio="Pedro Gómez")
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_DESAMBIGUACION

    respuesta2 = await maquina.recibir_respuesta_desambiguacion("1")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Pedro Luis Gómez Castro" in respuesta2.texto
    assert "$150.000" in respuesta2.texto
    assert respuesta.requiere_timeout is True


async def test_consultar_cuotas_con_letra_hint(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarCuotas(
            intencion="consultar_cuotas", socio="Hernando Ruiz Vargas", letra_id_hint="451"
        )
    )

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Hernando Ruiz Vargas" in respuesta.texto
    assert "Letra 451" in respuesta.texto
    assert "Cuotas pendientes: 1" in respuesta.texto
    assert respuesta.documento_pdf is not None
    assert respuesta.nombre_documento == "cuotas_letra_451.pdf"


async def test_consultar_cuotas_socio_sin_creditos(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarCuotas(intencion="consultar_cuotas", socio="María López", letra_id_hint=None)
    )

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "no tiene créditos activos" in respuesta.texto


# ── Resolución de nombres ─────────────────────────────────────────────────────


async def test_socio_no_encontrado_cancela_la_operacion(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="Nombre Inexistente", monto=1000)
    respuesta = await maquina.procesar_intencion(intencion)
    assert "No encontré" in respuesta.texto
    assert respuesta.cancelar_timeout is True
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert maquina.sesion.intencion is None


async def test_homonimos_disparan_desambiguacion_y_se_resuelve_con_seleccion(
    api_client: ApiClient,
) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="Pedro Gómez", monto=1000)

    respuesta = await maquina.procesar_intencion(intencion)
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_DESAMBIGUACION
    assert respuesta.requiere_timeout is True
    assert "1." in respuesta.texto and "2." in respuesta.texto

    respuesta2 = await maquina.recibir_respuesta_desambiguacion("1")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "Confirmas" in respuesta2.texto


async def test_desambiguacion_con_seleccion_invalida_reausenta_pregunta(
    api_client: ApiClient,
) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="Pedro Gómez", monto=1000)
    await maquina.procesar_intencion(intencion)

    respuesta = await maquina.recibir_respuesta_desambiguacion("99")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_DESAMBIGUACION
    assert respuesta.requiere_timeout is True
    assert "No entendí" in respuesta.texto


async def test_desambiguacion_se_puede_cancelar(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="Pedro Gómez", monto=1000)
    await maquina.procesar_intencion(intencion)

    await maquina.recibir_respuesta_desambiguacion("no")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert maquina.sesion.intencion is None


# ── Confirmación, ejecución, cancelación y timeout ───────────────────────────


async def test_flujo_completo_confirmacion_exitosa(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=50000)

    respuesta = await maquina.procesar_intencion(intencion)
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "$50.000" in respuesta.texto

    respuesta2 = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta2.documento_pdf is not None
    assert respuesta2.nombre_documento is not None
    assert respuesta2.cancelar_timeout is True
    assert maquina.sesion.intencion is None  # sesión reseteada tras completar


async def test_cancelacion_en_confirmacion_no_persiste_nada(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=50000)
    await maquina.procesar_intencion(intencion)

    respuesta = await maquina.recibir_confirmacion("no")
    assert "cancelada" in respuesta.texto.lower()
    assert respuesta.cancelar_timeout is True
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert maquina.sesion.intencion is None

    # el saldo de María no cambió
    socio = await api_client.get_socio(3)
    assert socio.saldo == 250000


async def test_respuesta_no_reconocida_en_confirmacion_repregunta(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=50000)
    await maquina.procesar_intencion(intencion)

    respuesta = await maquina.recibir_confirmacion("tal vez")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert respuesta.requiere_timeout is True


async def test_timeout_cancela_la_operacion(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=50000)
    await maquina.procesar_intencion(intencion)

    respuesta = maquina.cancelar_por_timeout()
    assert "inactividad" in respuesta.texto.lower()
    assert respuesta.cancelar_timeout is True
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert maquina.sesion.intencion is None


async def test_error_de_negocio_de_la_api_se_muestra_en_espanol_sin_stacktrace(
    api_client: ApiClient,
) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=999_999_999)
    await maquina.procesar_intencion(intencion)

    respuesta = await maquina.recibir_confirmacion("sí")
    assert "saldo suficiente" in respuesta.texto.lower()
    assert "Traceback" not in respuesta.texto
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE


async def test_idempotency_key_se_genera_una_sola_vez_al_confirmar(
    api_client: ApiClient,
) -> None:
    maquina = _maquina(api_client)
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=50000)
    await maquina.procesar_intencion(intencion)

    assert maquina.sesion.idempotency_key is None
    respuesta = await maquina.recibir_confirmacion("sí")
    # tras completar la operación con éxito la sesión se resetea
    assert maquina.sesion.idempotency_key is None
    assert respuesta.documento_pdf is not None

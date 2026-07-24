from coop_bot.api.cliente import ApiClient
from coop_bot.dialogo.estados import EstadoDialogo, MaquinaEstados, SesionDialogo
from coop_contracts.intenciones import (
    AporteItem,
    IntAmbigua,
    IntAyuda,
    IntConsultarCaja,
    IntConsultarCreditos,
    IntConsultarCuotas,
    IntConsultarFamilia,
    IntConsultarSocio,
    IntCrearCredito,
    IntDesconocida,
    IntDevolucionTotal,
    IntIncompleta,
    IntLiquidacionLetra,
    IntListarSocios,
    IntPagoSalario,
    IntPedirExcel,
    IntRegAporte,
    IntRegCombinado,
    IntRegPago,
    IntRegRetiro,
    PagoItem,
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
    assert "Cuánto" in respuesta.texto
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert maquina.sesion.texto_acumulado == "le recibí a Pedro"
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


async def test_ayuda_general_lista_capacidades(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(IntAyuda(intencion="ayuda", tema="general"))
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Aportes" in respuesta.texto
    assert "crédito" in respuesta.texto.lower()


async def test_ayuda_credito_es_especifica(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(IntAyuda(intencion="ayuda", tema="credito"))
    assert "cuotas" in respuesta.texto.lower()
    assert "1%" in respuesta.texto or "1 %" in respuesta.texto


async def test_crear_credito_pide_confirmacion(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntCrearCredito(intencion="crear_credito", socios=["Carmenza Suárez"], capital=1200000, n_cuotas=12)
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "Nuevo crédito" in respuesta.texto
    assert "1.200.000" in respuesta.texto
    assert "12 mensuales" in respuesta.texto
    assert "Letra:" in respuesta.texto  # muestra la letra que tomaría


async def test_crear_credito_flujo_completo(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    await maquina.procesar_intencion(
        IntCrearCredito(intencion="crear_credito", socios=["Carmenza Suárez"], capital=1200000, n_cuotas=12)
    )
    respuesta = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Crédito creado" in respuesta.texto
    assert "Letra" in respuesta.texto


async def test_devolucion_total_pide_confirmacion_reforzada(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntDevolucionTotal(intencion="devolucion_total", socio="Carmenza Suárez")
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "DEVOLUCIÓN TOTAL" in respuesta.texto
    assert "definitiva" in respuesta.texto


async def test_devolucion_total_flujo_completo(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    await maquina.procesar_intencion(
        IntDevolucionTotal(intencion="devolucion_total", socio="Carmenza Suárez")
    )
    respuesta = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Devolución total" in respuesta.texto
    assert "retirado" in respuesta.texto


# ── Consultas (B-15) ──────────────────────────────────────────────────────────


async def test_consultar_caja(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(IntConsultarCaja(intencion="consultar_caja"))

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "$5.830.000" in respuesta.texto
    assert "Administración total" in respuesta.texto
    assert "Papelería" in respuesta.texto
    assert "Por mora" in respuesta.texto
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
        IntConsultarCuotas(intencion="consultar_cuotas", socio="Hernando Ruiz Vargas", letra_id_hint="451")
    )

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Hernando Ruiz Vargas" in respuesta.texto
    assert "Letra 451" in respuesta.texto
    assert "Cuotas pendientes: 1" in respuesta.texto
    assert len(respuesta.documentos) == 1
    assert respuesta.documentos[0][0] == "cuotas_letra_451.pdf"


async def test_consultar_cuotas_socio_sin_creditos(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarCuotas(intencion="consultar_cuotas", socio="María López", letra_id_hint=None)
    )

    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "no tiene créditos activos" in respuesta.texto


async def test_listar_socios(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(IntListarSocios(intencion="listar_socios"))
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Socios" in respuesta.texto
    # El mock tiene varios socios; deben aparecer numerados
    assert "1." in respuesta.texto


async def test_consultar_creditos_de_un_socio(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarCreditos(intencion="consultar_creditos", socio="Pedro Antonio Gómez Ruiz")
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Letra 450" in respuesta.texto
    assert "cuotas" in respuesta.texto.lower()


async def test_consultar_familia_lista_miembros_y_saldos(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarFamilia(intencion="consultar_familia", socio="Pedro Antonio Gómez Ruiz")
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "Familia de" in respuesta.texto
    assert "María López Herrera" in respuesta.texto  # mismo familia_id en el mock
    assert "Saldo total" in respuesta.texto


async def test_consultar_familia_socio_sin_familia(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntConsultarFamilia(intencion="consultar_familia", socio="Carmenza Suárez Peña")
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "no tiene familia registrada" in respuesta.texto


async def test_liquidacion_letra_devuelve_pdf(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntLiquidacionLetra(intencion="liquidacion_letra", letras=[450])
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "450" in respuesta.texto
    assert len(respuesta.documentos) == 1
    assert respuesta.documentos[0][0] == "Liquidacion_actual_letra_450.pdf"


async def test_liquidacion_varias_letras_devuelve_varios_pdf(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntLiquidacionLetra(intencion="liquidacion_letra", letras=[450, 451])
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert len(respuesta.documentos) == 2
    nombres = [n for n, _ in respuesta.documentos]
    assert "Liquidacion_actual_letra_450.pdf" in nombres
    assert "Liquidacion_actual_letra_451.pdf" in nombres


async def test_liquidacion_letra_inexistente(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntLiquidacionLetra(intencion="liquidacion_letra", letras=[9999])
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "no encontré" in respuesta.texto.lower()


# ── Excel bajo pedido ──────────────────────────────────────────────────────


async def test_pedir_excel_sin_documento_previo(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(IntPedirExcel(intencion="pedir_excel"))
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "No tengo un documento reciente" in respuesta.texto


async def test_pedir_excel_de_liquidacion_actual(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    await maquina.procesar_intencion(IntLiquidacionLetra(intencion="liquidacion_letra", letras=[450]))
    respuesta = await maquina.procesar_intencion(IntPedirExcel(intencion="pedir_excel"))
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta.documento_pdf is not None
    assert respuesta.nombre_documento == "Liquidacion_actual_letra_450.xlsx"


async def test_pedir_excel_no_se_ofrece_con_varias_letras(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    await maquina.procesar_intencion(IntLiquidacionLetra(intencion="liquidacion_letra", letras=[450, 451]))
    respuesta = await maquina.procesar_intencion(IntPedirExcel(intencion="pedir_excel"))
    assert "No tengo un documento reciente" in respuesta.texto


async def test_pedir_excel_de_credito_nuevo(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    await maquina.procesar_intencion(
        IntCrearCredito(intencion="crear_credito", socios=["Carmenza Suárez"], capital=1200000, n_cuotas=12)
    )
    await maquina.recibir_confirmacion("sí")
    respuesta = await maquina.procesar_intencion(IntPedirExcel(intencion="pedir_excel"))
    assert respuesta.documento_pdf is not None
    assert respuesta.nombre_documento is not None
    assert respuesta.nombre_documento.startswith("Liquidacion_letra_")
    assert respuesta.nombre_documento.endswith(".xlsx")


async def test_pago_todas_letras_pide_confirmacion_y_ejecuta(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntRegPago(
            intencion="registrar_pago",
            recibi_de="Pedro Antonio Gómez Ruiz",
            pagos=[
                PagoItem(nombre="Pedro Antonio Gómez Ruiz", todas_las_letras=True, n_cuotas=1),
            ],
        )
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "450" in respuesta.texto

    respuesta2 = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta2.documento_pdf is not None


async def test_pago_por_letra_sin_nombre(api_client: ApiClient) -> None:
    # La letra manda: no hace falta el nombre del socio.
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntRegPago(
            intencion="registrar_pago",
            pagos=[PagoItem(letra_id_hint="450", n_cuotas=1)],
        )
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "450" in respuesta.texto

    respuesta2 = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta2.documento_pdf is not None


async def test_pago_dos_letras_diferentes_cuotas(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntRegPago(
            intencion="registrar_pago",
            pagos=[
                PagoItem(letra_id_hint="450", n_cuotas=1),
                PagoItem(letra_id_hint="451", n_cuotas=2),
            ],
        )
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "450" in respuesta.texto
    assert "451" in respuesta.texto


async def test_combinado_aportes_mas_pago_todas_letras(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntRegCombinado(
            intencion="registrar_combinado",
            recibi_de="Pedro Antonio Gómez Ruiz",
            aportes=[
                AporteItem(nombre="Pedro Antonio Gómez Ruiz", monto=30000),
                AporteItem(nombre="María López Herrera", monto=20000),
            ],
            pagos=[PagoItem(nombre="Pedro Antonio Gómez Ruiz", todas_las_letras=True, n_cuotas=1)],
        )
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "Aportes" in respuesta.texto
    assert "Pagos" in respuesta.texto

    respuesta2 = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta2.documento_pdf is not None


async def test_pago_salario_con_monto_explicito(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    respuesta = await maquina.procesar_intencion(
        IntPagoSalario(intencion="pago_salario", mes="junio", monto=1500000)
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "Junio" in respuesta.texto
    assert "1.500.000" in respuesta.texto

    respuesta2 = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "salario" in respuesta2.texto.lower()


async def test_pago_salario_operador_corrige_el_valor(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    await maquina.procesar_intencion(IntPagoSalario(intencion="pago_salario", mes="marzo", monto=1400000))
    # En vez de "sí", el operador dicta otro valor.
    respuesta = await maquina.recibir_confirmacion("1.600.000")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "1.600.000" in respuesta.texto


async def test_recibo_excede_limite_de_aportes(api_client: ApiClient) -> None:
    maquina = _maquina(api_client)
    aportes = [AporteItem(nombre="Pedro Antonio Gómez Ruiz", monto=10000) for _ in range(7)]
    respuesta = await maquina.procesar_intencion(
        IntRegAporte(intencion="registrar_aporte", recibi_de="Pedro Antonio Gómez Ruiz", aportes=aportes)
    )
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert "máximo 6" in respuesta.texto


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

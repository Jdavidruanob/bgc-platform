"""Tests de integración: intención -> resolución -> confirmación -> API -> PDF.

Ejercitan `MaquinaEstados` completa contra el mock server en memoria, sin
pasar por Telegram (esa capa se prueba por separado, ver test_telegram.py).

Los nombres usados aquí son los que no colisionan por fuzzy-match con ningún
otro socio del mock (a diferencia de "Pedro Gómez", que dispara
desambiguación por los homónimos id 1/2 — ese caso ya se cubre en
test_estados.py).
"""

from coop_bot.api.cliente import ApiClient
from coop_bot.dialogo.estados import EstadoDialogo, MaquinaEstados, SesionDialogo
from coop_contracts.intenciones import AporteItem, IntRegAporte, IntRegPago, PagoItem


async def test_flujo_completo_aporte_multiple(api_client: ApiClient) -> None:
    maquina = MaquinaEstados(SesionDialogo(chat_id=1), api_client)
    intencion = IntRegAporte(
        intencion="registrar_aporte",
        recibi_de="María López Herrera",
        aportes=[
            AporteItem(nombre="María López Herrera", monto=80000),
            AporteItem(nombre="Carmenza Suárez Peña", monto=50000),
        ],
    )

    respuesta_resumen = await maquina.procesar_intencion(intencion)
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "$80.000" in respuesta_resumen.texto
    assert "$50.000" in respuesta_resumen.texto

    respuesta_final = await maquina.recibir_confirmacion("confirmo")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta_final.documento_pdf is not None
    assert respuesta_final.nombre_documento is not None

    maria = await api_client.get_socio(3)
    carmenza = await api_client.get_socio(4)
    assert maria.saldo == 250000 + 80000
    assert carmenza.saldo == 180000 + 50000


async def test_flujo_completo_pago_con_letra_hint(api_client: ApiClient) -> None:
    maquina = MaquinaEstados(SesionDialogo(chat_id=1), api_client)
    intencion = IntRegPago(
        intencion="registrar_pago",
        recibi_de="Hernando Ruiz Vargas",
        pagos=[
            PagoItem(
                nombre="Hernando Ruiz Vargas",
                letra_id_hint="451",
                n_cuotas=1,
                abono_capital=0,
            )
        ],
    )

    respuesta_resumen = await maquina.procesar_intencion(intencion)
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_CONFIRMACION
    assert "Letra 451" in respuesta_resumen.texto

    respuesta_final = await maquina.recibir_confirmacion("sí")
    assert maquina.sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert respuesta_final.documento_pdf is not None

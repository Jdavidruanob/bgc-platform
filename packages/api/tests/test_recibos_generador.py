"""Tests del generador de xlsx: verifica que las celdas quedan bien llenas.

No depende de LibreOffice — abre el xlsx generado con openpyxl y valida.
"""

from __future__ import annotations

import io
from datetime import date

from coop_api.recibos.generador import (
    DatosRecibo,
    LineaAporte,
    LineaPago,
    SocioBasico,
    generar_xlsx_aporte,
    generar_xlsx_combinado,
    generar_xlsx_pago,
    generar_xlsx_retiro,
)
from openpyxl import load_workbook


def _abrir(xlsx: bytes):
    wb = load_workbook(io.BytesIO(xlsx))
    return wb.active


def test_aporte_llena_cabecera_y_totales() -> None:
    datos = DatosRecibo(
        recibo_id=42,
        fecha=date(2026, 7, 22),
        recibi_de=SocioBasico(nombres="Jose David", apellidos="Ruano Burbano"),
        aportes=[
            LineaAporte(
                socio=SocioBasico(nombres="Jose David", apellidos="Ruano Burbano"),
                monto=200000,
                saldo_anterior=5380000,
                saldo_nuevo=5580000,
            ),
        ],
        num_aportes_cobrables=1,
    )
    ws = _abrir(generar_xlsx_aporte(datos))
    assert ws["D4"].value == 42
    assert ws["I4"].value == "22/07/2026"
    assert "JOSE DAVID RUANO BURBANO" in str(ws["G6"].value)
    # Fila del primer aporte
    assert "200.000" in str(ws["H9"].value)
    assert "5.580.000" in str(ws["J9"].value)
    # Total y admin
    assert "200.000" in str(ws["H10"].value)
    assert "3.000" in str(ws["K12"].value)  # gastos_admin = 3000 * 1 aporte cobrable


def test_retiro_llena_campos_de_devolucion() -> None:
    socio = SocioBasico(nombres="María Elena", apellidos="Gómez Ruiz")
    datos = DatosRecibo(
        recibo_id=7,
        fecha=date(2026, 7, 22),
        recibi_de=socio,
        socio_retiro=socio,
        monto_retiro=350000,
    )
    ws = _abrir(generar_xlsx_retiro(datos))
    assert ws["B6"].value == 7
    assert "350.000" in str(ws["F6"].value)
    assert ws["F8"].value == "22/07/2026"
    assert "MARÍA ELENA" in str(ws["C14"].value)
    assert str(ws["C15"].value) == "GÓMEZ RUIZ"
    assert str(ws["C18"].value) == "MARÍA ELENA GÓMEZ RUIZ"


def test_pago_llena_una_cuota() -> None:
    datos = DatosRecibo(
        recibo_id=100,
        fecha=date(2026, 7, 22),
        recibi_de=SocioBasico(nombres="Pedro", apellidos="Gómez"),
        pagos=[
            LineaPago(
                socio=SocioBasico(nombres="Pedro", apellidos="Gómez"),
                letra_id=451,
                nro_cuota_inicio=3,
                nro_cuota_fin=3,
                total_cuotas_letra=12,
                saldo_capital_antes=800000,
                abono_capital=70000,
                interes=8000,
                saldo_capital_despues=730000,
            ),
        ],
    )
    ws = _abrir(generar_xlsx_pago(datos))
    assert ws["D4"].value == 100
    assert ws["F9"].value == 451
    assert ws["G9"].value == "3/12"
    assert "800.000" in str(ws["H9"].value)
    assert "70.000" in str(ws["I9"].value)
    assert "8.000" in str(ws["J9"].value)


def test_combinado_usa_matriz_x_y() -> None:
    datos = DatosRecibo(
        recibo_id=200,
        fecha=date(2026, 7, 22),
        recibi_de=SocioBasico(nombres="Karoll", apellidos="Marcela"),
        aportes=[
            LineaAporte(
                socio=SocioBasico(nombres="Karoll", apellidos="Marcela"),
                monto=100000,
                saldo_anterior=500000,
                saldo_nuevo=600000,
            ),
        ],
        pagos=[
            LineaPago(
                socio=SocioBasico(nombres="Karoll", apellidos="Marcela"),
                letra_id=450,
                nro_cuota_inicio=2,
                nro_cuota_fin=3,
                total_cuotas_letra=10,
                saldo_capital_antes=900000,
                abono_capital=150000,
                interes=12000,
                saldo_capital_despues=750000,
            ),
        ],
        num_aportes_cobrables=1,
    )
    ws = _abrir(generar_xlsx_combinado(datos))
    assert ws["D4"].value == 200
    # Aporte en fila 9
    assert "100.000" in str(ws["H9"].value)
    # Pago 3 filas después del total de aportes (row_total=10, start_creditos=13)
    assert ws["F13"].value == 450
    assert ws["G13"].value == "2-3/10"

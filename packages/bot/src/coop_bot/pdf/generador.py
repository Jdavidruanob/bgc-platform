"""Generación de comprobantes en PDF (recibos y tablas de cuotas) con reportlab."""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from coop_contracts.respuestas import (
    AportesResponse,
    CombinadoResponse,
    CuotaPendiente,
    PagoResultItem,
    PagosResponse,
    RetiroResponse,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from coop_bot.dialogo.resumen import formatear_monto

_MARGEN_X = 50
_Y_INICIAL = 740
_INTERLINEA = 18


@dataclass
class LineaRecibo:
    socio: str
    concepto: str
    monto: int
    detalle: str | None = None


@dataclass
class ReciboData:
    recibo_id: int
    fecha: str
    recibi_de: str
    lineas: list[LineaRecibo] = field(default_factory=list)
    total: int = 0
    saldo_caja_nuevo: int = 0


# ── Adaptadores desde las respuestas de coop-api ──────────────────────────────


def recibo_desde_aportes(resp: AportesResponse) -> ReciboData:
    lineas = [LineaRecibo(socio=a.nombre_completo, concepto="Aporte", monto=a.monto) for a in resp.aportes]
    total = sum(a.monto for a in resp.aportes)
    return ReciboData(
        recibo_id=resp.recibo_id,
        fecha=resp.fecha,
        recibi_de=resp.recibi_de.nombre_completo,
        lineas=lineas,
        total=total,
        saldo_caja_nuevo=resp.saldo_caja_nuevo,
    )


def recibo_desde_retiro(resp: RetiroResponse) -> ReciboData:
    lineas = [
        LineaRecibo(
            socio=resp.socio.nombre_completo,
            concepto="Retiro",
            monto=resp.monto_retirado,
        )
    ]
    return ReciboData(
        recibo_id=resp.recibo_id,
        fecha=resp.fecha,
        recibi_de=resp.socio.nombre_completo,
        lineas=lineas,
        total=resp.monto_retirado,
        saldo_caja_nuevo=resp.saldo_caja_nuevo,
    )


def _concepto_pago(p: PagoResultItem) -> str:
    cuotas = ",".join(str(n) for n in p.cuotas_pagadas)
    return f"Pago letra {p.letra_id} (cuotas {cuotas})"


def recibo_desde_pagos(resp: PagosResponse) -> ReciboData:
    lineas = [
        LineaRecibo(socio=p.nombre_completo, concepto=_concepto_pago(p), monto=p.total_pagado)
        for p in resp.pagos
    ]
    total = sum(p.total_pagado for p in resp.pagos)
    return ReciboData(
        recibo_id=resp.recibo_id,
        fecha=resp.fecha,
        recibi_de=resp.recibi_de.nombre_completo,
        lineas=lineas,
        total=total,
        saldo_caja_nuevo=resp.saldo_caja_nuevo,
    )


def recibo_desde_combinado(resp: CombinadoResponse) -> ReciboData:
    lineas = [LineaRecibo(socio=a.nombre_completo, concepto="Aporte", monto=a.monto) for a in resp.aportes]
    lineas += [
        LineaRecibo(socio=p.nombre_completo, concepto=_concepto_pago(p), monto=p.total_pagado)
        for p in resp.pagos
    ]
    total = sum(a.monto for a in resp.aportes) + sum(p.total_pagado for p in resp.pagos)
    return ReciboData(
        recibo_id=resp.recibo_id,
        fecha=resp.fecha,
        recibi_de=resp.recibi_de.nombre_completo,
        lineas=lineas,
        total=total,
        saldo_caja_nuevo=resp.saldo_caja_nuevo,
    )


# ── Generación de PDF ─────────────────────────────────────────────────────────


def generar_pdf_recibo(datos: ReciboData) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y: float = _Y_INICIAL

    c.setFont("Helvetica-Bold", 16)
    c.drawString(_MARGEN_X, y, f"Recibo N° {datos.recibo_id}")
    y -= _INTERLINEA * 1.5

    c.setFont("Helvetica", 11)
    c.drawString(_MARGEN_X, y, f"Fecha: {datos.fecha}")
    y -= _INTERLINEA
    c.drawString(_MARGEN_X, y, f"Recibí de: {datos.recibi_de}")
    y -= _INTERLINEA * 1.5

    c.setFont("Helvetica-Bold", 11)
    c.drawString(_MARGEN_X, y, "Detalle:")
    y -= _INTERLINEA
    c.setFont("Helvetica", 11)
    for linea in datos.lineas:
        texto = f"- {linea.socio} | {linea.concepto}: {formatear_monto(linea.monto)}"
        c.drawString(_MARGEN_X, y, texto)
        y -= _INTERLINEA

    y -= _INTERLINEA * 0.5
    c.setFont("Helvetica-Bold", 12)
    c.drawString(_MARGEN_X, y, f"Total: {formatear_monto(datos.total)}")
    y -= _INTERLINEA
    c.setFont("Helvetica", 10)
    c.drawString(_MARGEN_X, y, f"Saldo en caja: {formatear_monto(datos.saldo_caja_nuevo)}")

    c.showPage()
    c.save()
    return buffer.getvalue()


def generar_pdf_tabla_cuotas(letra_id: int, cuotas: list[CuotaPendiente], deuda_total: int) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y: float = _Y_INICIAL

    c.setFont("Helvetica-Bold", 16)
    c.drawString(_MARGEN_X, y, f"Cuotas pendientes - Letra {letra_id}")
    y -= _INTERLINEA * 1.5

    c.setFont("Helvetica-Bold", 11)
    c.drawString(_MARGEN_X, y, f"Deuda total actual: {formatear_monto(deuda_total)}")
    y -= _INTERLINEA * 1.5

    c.setFont("Helvetica-Bold", 10)
    c.drawString(_MARGEN_X, y, "Cuota | Vencimiento | Valor | Interés | Mora | Estado")
    y -= _INTERLINEA
    c.setFont("Helvetica", 10)
    for cuota in cuotas:
        texto = (
            f"{cuota.nro_cuota} | {cuota.fecha_vencimiento} | "
            f"{formatear_monto(cuota.valor_cuota)} | {formatear_monto(cuota.interes_mes)} | "
            f"{formatear_monto(cuota.mora_estimada)} | {cuota.estado}"
        )
        c.drawString(_MARGEN_X, y, texto)
        y -= _INTERLINEA

    c.showPage()
    c.save()
    return buffer.getvalue()


def nombre_archivo_recibo(recibo_id: int) -> str:
    return f"recibo_{recibo_id}.pdf"


def nombre_archivo_cuotas(letra_id: int) -> str:
    return f"cuotas_letra_{letra_id}.pdf"

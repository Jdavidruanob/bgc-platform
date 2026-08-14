"""Genera y envía la liquidación al día de hoy de un crédito, para el
asistente de WhatsApp. Reusa el mismo generador que ya usa
`GET /creditos/{letra_id}/liquidacion-actual/pdf` — ver
`coop_api.routers.creditos._construir_datos_liquidacion_actual`."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from coop_core.db.connection import DbConnection

from coop_api.asistente.whatsapp_cliente import ClienteWhatsApp, Documento
from coop_api.recibos.generador import DatosLiquidacion, generar_xlsx_liquidacion
from coop_api.recibos.pdf_converter import PdfConversionError, xlsx_a_pdf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorLiquidacion:
    codigo: str


def preparar_datos_liquidacion(db: DbConnection, letra_id: int) -> DatosLiquidacion | ErrorLiquidacion:
    """Se corre síncronamente dentro del request (2 queries, rápido) para
    tener los datos listos ANTES de encolar la parte lenta (LibreOffice) en
    una BackgroundTask — la conexión `db` del request se cierra apenas
    termina, así que la tarea de fondo nunca puede usarla."""
    from coop_api.routers.creditos import _construir_datos_liquidacion_actual

    resultado = _construir_datos_liquidacion_actual(letra_id, db)
    if isinstance(resultado, str):
        return ErrorLiquidacion(resultado)
    return resultado


def enviar_liquidacion_pdf(
    cliente: ClienteWhatsApp,
    numero_meta: str,
    letra_id: int,
    datos: DatosLiquidacion,
    fecha_hoy_larga: str,
) -> None:
    """Pensada para correr en una `BackgroundTasks`: nunca toca la base de
    datos, solo genera el documento a partir de `datos` (ya armado) y lo
    envía. Cualquier falla queda contenida acá — el socio ya recibió el aviso
    de "dame un momento" y no hay nada más que devolver."""
    from coop_api.asistente import copy

    try:
        xlsx = generar_xlsx_liquidacion(datos)
        pdf = xlsx_a_pdf(xlsx)
    except PdfConversionError:
        logger.exception("No se pudo convertir a PDF la liquidación de la letra %s", letra_id)
        cliente.enviar_texto(numero_meta, copy.liquidacion_no_disponible())
        return
    except Exception:
        logger.exception("Error generando la liquidación de la letra %s", letra_id)
        cliente.enviar_texto(numero_meta, copy.liquidacion_no_disponible())
        return

    documento = Documento(
        contenido=pdf,
        nombre_archivo=f"Liquidacion_letra_{letra_id}.pdf",
        mime="application/pdf",
        caption=copy.liquidacion_caption(letra_id, fecha_hoy_larga),
    )
    if not cliente.enviar_documento(numero_meta, documento):
        logger.error("Meta rechazó el envío de la liquidación de la letra %s a %s", letra_id, numero_meta)

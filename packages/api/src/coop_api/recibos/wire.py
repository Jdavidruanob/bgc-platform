"""Puente entre el resultado de un servicio de operación y la persistencia del
recibo (xlsx + pdf). Se llama desde cada endpoint de operaciones justo antes
de `db.commit()`.

Los errores de LibreOffice se propagan como HTTPException 500 para que el
cliente lo interprete como error interno reintenteble; la escritura en la tabla
va dentro de la misma transacción, así que si falla, no queda estado a medias.
"""

from __future__ import annotations

import logging
import shutil
from datetime import date, datetime
from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.creditos_repo import CreditosRepository

from coop_api.recibos import generador
from coop_api.recibos.generador import (
    CuotaLiquidacion,
    DatosLiquidacion,
    DatosRecibo,
    DatosSalario,
    LineaAporte,
    LineaPago,
    SocioBasico,
)
from coop_api.recibos.pdf_converter import PdfConversionError, xlsx_a_pdf
from coop_api.recibos.repositorio import (
    LiquidacionesArchivosRepository,
    RecibosArchivosRepository,
    TipoRecibo,
)

logger = logging.getLogger(__name__)


def _soffice_disponible() -> bool:
    return shutil.which("soffice") is not None or shutil.which("libreoffice") is not None


def _a_date(fecha_str_o_dt: str | date | datetime) -> date:
    if isinstance(fecha_str_o_dt, datetime):
        return fecha_str_o_dt.date()
    if isinstance(fecha_str_o_dt, date):
        return fecha_str_o_dt
    return datetime.fromisoformat(fecha_str_o_dt).date()


def _socio(dato: dict[str, Any]) -> SocioBasico:
    return SocioBasico(nombres=str(dato["nombres"]), apellidos=str(dato["apellidos"]))


def _aporte(a: dict[str, Any]) -> LineaAporte:
    return LineaAporte(
        socio=SocioBasico(nombres=str(a["nombres"]), apellidos=str(a["apellidos"])),
        monto=int(a["monto"]),
        saldo_anterior=int(a["saldo_anterior"]),
        saldo_nuevo=int(a["saldo_nuevo"]),
    )


def _pago(p: dict[str, Any], total_cuotas_letra: int) -> LineaPago:
    cuotas = p.get("cuotas_pagadas") or []
    inicio: int | str = int(cuotas[0]) if cuotas else "ABONO"
    fin: int | str = int(cuotas[-1]) if cuotas else "ABONO"
    return LineaPago(
        socio=SocioBasico(nombres=str(p["nombres"]), apellidos=str(p["apellidos"])),
        letra_id=int(p["letra_id"]),
        nro_cuota_inicio=inicio,
        nro_cuota_fin=fin,
        total_cuotas_letra=total_cuotas_letra,
        saldo_capital_antes=int(p["saldo_capital_antes_pago"]),
        abono_capital=int(p["valor_capital_consolidado"]),
        interes=int(p["interes_consolidado"]),
        saldo_capital_despues=int(p["saldo_capital_despues_pago"]),
        mora=int(p.get("mora_consolidada", 0)),
    )


def _total_cuotas(db: DbConnection, letra_id: int) -> int:
    fila = CreditosRepository(db).find_by_letra(letra_id)
    return int(fila["no_cuotas"]) if fila else 0


def _persistir(db: DbConnection, recibo_id: int, tipo: TipoRecibo, xlsx: bytes) -> None:
    if not _soffice_disponible():
        # Entorno sin LibreOffice (tests, dev sin instalarlo). El xlsx queda
        # generado por si se prueba visualmente, pero se salta la persistencia
        # para no romper el flujo. En producción soffice siempre está.
        logger.warning("soffice no disponible; se salta la persistencia del recibo %s", recibo_id)
        return
    try:
        pdf = xlsx_a_pdf(xlsx)
    except PdfConversionError:
        logger.exception("Fallo al convertir xlsx a PDF para el recibo %s", recibo_id)
        raise
    RecibosArchivosRepository(db).guardar(recibo_id, tipo, xlsx, pdf)


def guardar_recibo_salario(
    db: DbConnection,
    recibo_id: int,
    fecha: str,
    mes: str,
    monto: int,
) -> None:
    datos = DatosSalario(
        recibo_id=recibo_id,
        valor=monto,
        fecha=_a_date(fecha),
        mes=mes,
    )
    xlsx = generador.generar_xlsx_salario(datos)
    _persistir(db, recibo_id, "salario", xlsx)


def guardar_recibo_aporte(
    db: DbConnection,
    resultado: dict[str, Any],
    recibi_de: dict[str, Any],
) -> None:
    datos = DatosRecibo(
        recibo_id=int(resultado["recibo_id"]),
        fecha=_a_date(resultado["fecha"]),
        recibi_de=_socio(recibi_de),
        aportes=[_aporte(a) for a in resultado["aportes"]],
        num_aportes_cobrables=int(resultado["count_cobrables"]),
    )
    xlsx = generador.generar_xlsx_aporte(datos)
    _persistir(db, datos.recibo_id, "aporte", xlsx)


def guardar_recibo_retiro(
    db: DbConnection,
    resultado: dict[str, Any],
    socio: dict[str, Any],
) -> None:
    datos = DatosRecibo(
        recibo_id=int(resultado["recibo_id"]),
        fecha=_a_date(resultado["fecha"]),
        recibi_de=_socio(socio),
        socio_retiro=_socio(socio),
        monto_retiro=int(resultado["monto"]),
    )
    xlsx = generador.generar_xlsx_retiro(datos)
    _persistir(db, datos.recibo_id, "retiro", xlsx)


def guardar_recibo_devolucion_total(
    db: DbConnection,
    resultado: dict[str, Any],
    socio: dict[str, Any],
) -> None:
    datos = DatosRecibo(
        recibo_id=int(resultado["recibo_id"]),
        fecha=_a_date(resultado["fecha"]),
        recibi_de=_socio(socio),
        socio_retiro=_socio(socio),
        monto_retiro=int(resultado["monto"]),
    )
    xlsx = generador.generar_xlsx_devolucion_total(datos)
    _persistir(db, datos.recibo_id, "devolucion_total", xlsx)


def guardar_recibo_pago(
    db: DbConnection,
    resultado: dict[str, Any],
    recibi_de: dict[str, Any],
) -> None:
    pagos = [_pago(p, _total_cuotas(db, int(p["letra_id"]))) for p in resultado["pagos"]]
    datos = DatosRecibo(
        recibo_id=int(resultado["recibo_id"]),
        fecha=_a_date(resultado["fecha"]),
        recibi_de=_socio(recibi_de),
        pagos=pagos,
    )
    xlsx = generador.generar_xlsx_pago(datos)
    _persistir(db, datos.recibo_id, "pago", xlsx)


def guardar_recibo_combinado(
    db: DbConnection,
    resultado: dict[str, Any],
    recibi_de: dict[str, Any],
    n_cobrables: int,
) -> None:
    pagos = [_pago(p, _total_cuotas(db, int(p["letra_id"]))) for p in resultado["pagos"]]
    datos = DatosRecibo(
        recibo_id=int(resultado["recibo_id"]),
        fecha=_a_date(resultado["fecha"]),
        recibi_de=_socio(recibi_de),
        aportes=[_aporte(a) for a in resultado["aportes"]],
        pagos=pagos,
        num_aportes_cobrables=n_cobrables,
    )
    xlsx = generador.generar_xlsx_combinado(datos)
    _persistir(db, datos.recibo_id, "combinado", xlsx)


def guardar_liquidacion_credito(db: DbConnection, resultado: dict[str, Any]) -> None:
    """Genera la liquidación xlsx→pdf y la persiste. El crédito ya fue creado y
    commiteado por CreditoService; esta persistencia va en su propia transacción.
    Si LibreOffice no está (dev/tests), se salta sin romper.
    """
    if not _soffice_disponible():
        logger.warning("soffice no disponible; se salta la liquidación del crédito %s", resultado["letra_id"])
        return

    tabla = resultado["tabla_amortizacion"]
    valor_cuota_base = int(tabla[0]["valor_cuota"]) if tabla else 0
    datos = DatosLiquidacion(
        letra_id=int(resultado["letra_id"]),
        capital=int(resultado["capital"]),
        interes=float(resultado["interes"]),
        n_cuotas=int(resultado["n_cuotas"]),
        fecha_inicio=_a_date(resultado["fecha"]),
        socios=[
            SocioBasico(nombres=str(s["nombres"]), apellidos=str(s["apellidos"])) for s in resultado["socios"]
        ],
        valor_cuota_base=valor_cuota_base,
        cuotas=[
            CuotaLiquidacion(
                nro_cuota=int(c["nro_cuota"]),
                fecha_vencimiento=str(c["fecha_vencimiento"]),
                valor_cuota=int(c["valor_cuota"]),
                interes_mes=int(c["interes_mes"]),
                cuota_mensual=int(c["cuota_mensual"]),
                saldo_capital=int(c["saldo_capital"]),
            )
            for c in tabla
        ],
    )
    xlsx = generador.generar_xlsx_liquidacion(datos)
    try:
        pdf = xlsx_a_pdf(xlsx)
    except PdfConversionError:
        logger.exception("Fallo al convertir la liquidación del crédito %s", datos.letra_id)
        raise
    LiquidacionesArchivosRepository(db).guardar(datos.letra_id, xlsx, pdf)
    db.commit()

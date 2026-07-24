from datetime import datetime

from coop_contracts.respuestas import (
    CreditoDetalle,
    CreditoSocio,
    CuotaPendiente,
    CuotasPendientesResponse,
)
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.repositories.socios_repo import SociosRepository
from coop_core.services.amortization import calculate_mora
from coop_core.utils.fecha import get_hoy
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from coop_api.deps import AuthDep, DbDep
from coop_api.errors import not_found
from coop_api.recibos.generador import (
    CuotaLiquidacion,
    DatosLiquidacion,
    SocioBasico,
    generar_xlsx_liquidacion,
)
from coop_api.recibos.pdf_converter import PdfConversionError, xlsx_a_pdf
from coop_api.recibos.repositorio import LiquidacionesArchivosRepository

router = APIRouter(prefix="/creditos", tags=["creditos"])


@router.get("/proxima-letra")
def get_proxima_letra(db: DbDep, _auth: AuthDep) -> dict[str, int]:
    """Número de letra que tomaría el próximo crédito (para mostrarlo en la
    confirmación antes de crearlo)."""
    return {"letra": CreditosRepository(db).next_letra()}


@router.get("/{letra_id}", response_model=None)
def get_credito(letra_id: int, db: DbDep, _auth: AuthDep) -> CreditoDetalle | JSONResponse:
    """Detalle de un crédito por su letra, incluyendo sus socios titulares.
    Sirve para que el bot resuelva la letra → socio (la letra es única)."""
    creditos_repo = CreditosRepository(db)
    credito = creditos_repo.find_by_letra(letra_id)
    if credito is None:
        return not_found("LETRA_NO_ENCONTRADA", f"No existe un crédito con letra {letra_id}.")
    socios_repo = SociosRepository(db)
    socios = []
    for sid in creditos_repo.get_socio_ids(letra_id):
        s = socios_repo.find_by_id(sid)
        if s is not None:
            socios.append(CreditoSocio(id=int(s["id"]), nombre_completo=f"{s['nombres']} {s['apellidos']}"))
    return CreditoDetalle(
        letra_id=letra_id,
        capital=int(credito["capital"]),
        interes_tasa=float(credito["interes"]),
        n_cuotas_total=int(credito["no_cuotas"]),
        fecha_inicio=str(credito["fecha_inicio"]),
        socios=socios,
    )


@router.get("/{letra_id}/cuotas-pendientes", response_model=None)
def get_cuotas_pendientes(
    letra_id: int, db: DbDep, _auth: AuthDep
) -> CuotasPendientesResponse | JSONResponse:
    creditos_repo = CreditosRepository(db)
    if creditos_repo.find_by_letra(letra_id) is None:
        return not_found("LETRA_NO_ENCONTRADA", f"No existe un crédito con letra {letra_id}.")

    liquidaciones_repo = LiquidacionesRepository(db)
    from coop_core.repositories.config_repo import ConfigRepository

    config_repo = ConfigRepository(db)
    tasa_mora = float(config_repo.get("porcentaje_mora") or "0.02")
    hoy = get_hoy()

    pendientes = liquidaciones_repo.find_pending(letra_id)
    cuotas: list[CuotaPendiente] = []
    deuda_total = 0

    for c in pendientes:
        mora = calculate_mora(str(c["fecha_vencimiento"]), hoy, int(c["valor_cuota"]), tasa_mora)
        from datetime import datetime

        fv = datetime.strptime(str(c["fecha_vencimiento"]), "%Y-%m-%d").date()
        estado = "vencida" if fv < hoy else ("vigente" if fv == hoy else "futuro")
        cuota_total = int(c["cuota_mensual"]) + mora
        deuda_total += cuota_total
        cuotas.append(
            CuotaPendiente(
                nro_cuota=int(c["nro_cuota"]),
                fecha_vencimiento=str(c["fecha_vencimiento"]),
                valor_cuota=int(c["valor_cuota"]),
                interes_mes=int(c["interes_mes"]),
                cuota_mensual=int(c["cuota_mensual"]),
                mora_estimada=mora,
                estado=estado,
            )
        )

    return CuotasPendientesResponse(
        letra_id=letra_id,
        deuda_total_actual=deuda_total,
        cuotas_pendientes=cuotas,
    )


@router.get("/{letra_id}/liquidacion/pdf", response_model=None)
def descargar_liquidacion_pdf(letra_id: int, db: DbDep, _auth: AuthDep) -> Response | JSONResponse:
    pdf = LiquidacionesArchivosRepository(db).obtener_pdf(letra_id)
    if pdf is None:
        return not_found("LIQUIDACION_NO_ENCONTRADA", f"No hay liquidación PDF para la letra {letra_id}.")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Liquidacion_letra_{letra_id}.pdf"'},
    )


@router.get("/{letra_id}/liquidacion/xlsx", response_model=None)
def descargar_liquidacion_xlsx(letra_id: int, db: DbDep, _auth: AuthDep) -> Response | JSONResponse:
    xlsx = LiquidacionesArchivosRepository(db).obtener_xlsx(letra_id)
    if xlsx is None:
        return not_found("LIQUIDACION_NO_ENCONTRADA", f"No hay liquidación Excel para la letra {letra_id}.")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Liquidacion_letra_{letra_id}.xlsx"'},
    )


def _construir_datos_liquidacion_actual(letra_id: int, db: DbDep) -> DatosLiquidacion | str:
    """Devuelve los datos de la liquidación actual, o un código de error
    ('LETRA_NO_ENCONTRADA' | 'SIN_CUOTAS') si no se puede construir."""
    credito = CreditosRepository(db).find_by_letra(letra_id)
    if credito is None:
        return "LETRA_NO_ENCONTRADA"

    cuotas = LiquidacionesRepository(db).find_all_by_letra(letra_id)
    if not cuotas:
        return "SIN_CUOTAS"

    socios_nombres = str(credito.get("socios_nombres") or "").split(", ")
    fecha_inicio_raw = str(credito["fecha_inicio"])[:10]
    fecha_inicio = datetime.strptime(fecha_inicio_raw, "%Y-%m-%d").date()

    return DatosLiquidacion(
        letra_id=letra_id,
        capital=int(credito["capital"]),
        interes=float(credito["interes"]),
        n_cuotas=int(credito["no_cuotas"]),
        fecha_inicio=fecha_inicio,
        socios=[SocioBasico(nombres=n, apellidos="") for n in socios_nombres if n],
        valor_cuota_base=int(cuotas[0]["valor_cuota"]),
        cuotas=[
            CuotaLiquidacion(
                nro_cuota=int(c["nro_cuota"]),
                fecha_vencimiento=str(c["fecha_vencimiento"]),
                valor_cuota=int(c["valor_cuota"]),
                interes_mes=int(c["interes_mes"]),
                cuota_mensual=int(c["cuota_mensual"]),
                saldo_capital=int(c["saldo_capital"]),
                fecha_pago=str(c["fecha_pago"]) if c["fecha_pago"] else "",
            )
            for c in cuotas
        ],
    )


def _error_liquidacion_actual(codigo: str, letra_id: int) -> JSONResponse:
    if codigo == "LETRA_NO_ENCONTRADA":
        return not_found("LETRA_NO_ENCONTRADA", f"No existe un crédito con letra {letra_id}.")
    return not_found("SIN_CUOTAS", f"El crédito {letra_id} no tiene cuotas registradas.")


@router.get("/{letra_id}/liquidacion-actual/pdf", response_model=None)
def descargar_liquidacion_actual(letra_id: int, db: DbDep, _auth: AuthDep) -> Response | JSONResponse:
    """Genera al vuelo la liquidación con el estado ACTUAL del crédito (cuotas
    pagadas con su fecha). No se guarda en la base — es un documento desechable
    para consulta."""
    datos = _construir_datos_liquidacion_actual(letra_id, db)
    if isinstance(datos, str):
        return _error_liquidacion_actual(datos, letra_id)

    xlsx = generar_xlsx_liquidacion(datos)
    try:
        pdf = xlsx_a_pdf(xlsx)
    except PdfConversionError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "codigo": "PDF_NO_DISPONIBLE",
                    "mensaje": "No se pudo generar el PDF de la liquidación.",
                    "detalle": None,
                }
            },
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Liquidacion_actual_letra_{letra_id}.pdf"'},
    )


@router.get("/{letra_id}/liquidacion-actual/xlsx", response_model=None)
def descargar_liquidacion_actual_xlsx(letra_id: int, db: DbDep, _auth: AuthDep) -> Response | JSONResponse:
    """Misma liquidación actual, pero en Excel. Se genera al vuelo, tampoco se
    guarda (documento desechable)."""
    datos = _construir_datos_liquidacion_actual(letra_id, db)
    if isinstance(datos, str):
        return _error_liquidacion_actual(datos, letra_id)

    xlsx = generar_xlsx_liquidacion(datos)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Liquidacion_actual_letra_{letra_id}.xlsx"'},
    )

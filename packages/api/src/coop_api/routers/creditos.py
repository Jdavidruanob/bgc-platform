from coop_contracts.respuestas import CuotaPendiente, CuotasPendientesResponse
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.services.amortization import calculate_mora
from coop_core.utils.fecha import get_hoy
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from coop_api.deps import AuthDep, DbDep
from coop_api.errors import not_found

router = APIRouter(prefix="/creditos", tags=["creditos"])


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

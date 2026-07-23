from coop_contracts.respuestas import CajaEstado
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.recibos_repo import RecibosRepository
from coop_core.services.caja_service import CajaService
from fastapi import APIRouter

from coop_api.deps import AuthDep, DbDep

router = APIRouter(prefix="/caja", tags=["caja"])


@router.get("")
def get_caja(db: DbDep, _auth: AuthDep) -> CajaEstado:
    config = ConfigRepository(db)
    auxiliar = AuxiliarRepository(db)
    recibos = RecibosRepository(db)
    svc = CajaService(config, auxiliar, recibos)
    papeleria = svc.get_papeleria()
    mora_acumulada = svc.get_mora_acumulada()
    return CajaEstado(
        saldo_en_caja=svc.get_saldo_caja(),
        total_admin=papeleria,
        porcentaje_mora=svc.get_porcentaje_mora(),
        papeleria=papeleria,
        mora_acumulada=mora_acumulada,
        administracion_total=papeleria + mora_acumulada,
    )

from coop_contracts.respuestas import CajaEstado
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.services.caja_service import CajaService
from fastapi import APIRouter

from coop_api.deps import AuthDep, DbDep

router = APIRouter(prefix="/caja", tags=["caja"])


@router.get("")
def get_caja(db: DbDep, _auth: AuthDep) -> CajaEstado:
    config = ConfigRepository(db)
    auxiliar = AuxiliarRepository(db)
    svc = CajaService(config, auxiliar)
    return CajaEstado(
        saldo_en_caja=svc.get_saldo_caja(),
        total_admin=svc.get_total_admin(),
        porcentaje_mora=svc.get_porcentaje_mora(),
    )

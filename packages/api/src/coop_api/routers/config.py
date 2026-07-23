from coop_contracts.respuestas import SalarioConfig
from coop_core.repositories.config_repo import ConfigRepository
from fastapi import APIRouter

from coop_api.deps import AuthDep, DbDep

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/salario")
def get_salario(db: DbDep, _auth: AuthDep) -> SalarioConfig:
    """Salario guardado (salario mínimo). El bot lo muestra y el operador lo
    confirma o modifica al pagar; el valor confirmado se guarda de nuevo."""
    config = ConfigRepository(db)
    return SalarioConfig(salario_guardado=config.get_int("salario_minimo"))

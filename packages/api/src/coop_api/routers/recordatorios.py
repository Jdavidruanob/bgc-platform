from fastapi import APIRouter

from coop_api.deps import AuthDep, DbDep
from coop_api.recordatorios_wire import generar_recordatorios_cuotas_proximas

router = APIRouter(prefix="/recordatorios", tags=["recordatorios"])


@router.post("/cuotas-proximas")
def post_recordatorios_cuotas_proximas(db: DbDep, _auth: AuthDep) -> dict[str, int]:
    """Encola los recordatorios de mora próxima del día: cuotas que hoy
    cumplen su fecha de pago y aún no entraron en mora (ver ADR-010).
    Pensado para llamarse una vez al día desde un job externo; es idempotente."""
    encoladas = generar_recordatorios_cuotas_proximas(db)
    db.commit()
    return {"encoladas": encoladas}

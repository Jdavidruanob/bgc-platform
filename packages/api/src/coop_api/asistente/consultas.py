"""Las 3 consultas de solo lectura del asistente. Composición fina de repos
de coop-core existentes — ningún cálculo de negocio se reimplementa aquí."""

from __future__ import annotations

from datetime import date
from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.services.amortization import build_cuotas_pendientes_detalle


def tasa_mora(db: DbConnection) -> float:
    valor = ConfigRepository(db).get("porcentaje_mora")
    return float(valor or "0.02")


def letras_activas(db: DbConnection, socio_id: int) -> list[int]:
    """Letras de los créditos activos del socio (excluye los ya saldados),
    ordenadas para que el orden de los botones/filas sea siempre el mismo."""
    creditos = CreditosRepository(db).find_active_by_socio_id(socio_id)
    return sorted(int(c["letra"]) for c in creditos)


def cuotas_pendientes_de_letra(db: DbConnection, letra_id: int, hoy: date) -> list[dict[str, Any]]:
    """Cuotas pendientes de una letra con su mora vigente calculada — el
    mismo cálculo que usa `GET /creditos/{letra_id}/cuotas-pendientes`."""
    pendientes = LiquidacionesRepository(db).find_pending(letra_id)
    return build_cuotas_pendientes_detalle(pendientes, hoy, tasa_mora(db))

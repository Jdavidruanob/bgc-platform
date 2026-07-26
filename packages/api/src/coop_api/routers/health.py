from coop_contracts.respuestas import HealthOk
from fastapi import APIRouter

from coop_api import entorno

router = APIRouter()


@router.get("/health")
def health() -> HealthOk:
    return HealthOk(version="0.1.0", entorno=entorno.get_entorno())

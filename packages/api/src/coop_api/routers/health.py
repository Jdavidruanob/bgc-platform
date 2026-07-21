from coop_contracts.respuestas import HealthOk
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> HealthOk:
    return HealthOk(version="0.1.0")

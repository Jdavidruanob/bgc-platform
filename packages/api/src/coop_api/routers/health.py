from fastapi import APIRouter

from coop_contracts.respuestas import HealthOk

router = APIRouter()


@router.get("/health")
def health() -> HealthOk:
    return HealthOk(version="0.1.0")

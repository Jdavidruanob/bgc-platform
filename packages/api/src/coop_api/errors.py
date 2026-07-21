"""Formato uniforme de errores según docs/05."""

from __future__ import annotations

from coop_contracts.respuestas import ErrorDetail, ErrorResponse
from fastapi.responses import JSONResponse

_VALUE_ERROR_CODES: dict[str, str] = {
    "saldo suficiente": "SALDO_INSUFICIENTE",
    "cuotas pendientes": "CUOTAS_INSUFICIENTES",
    "Abono insuficiente": "ABONO_INSUFICIENTE",
    "Abono incompleto": "ABONO_INCOMPLETO",
    "solo una opción": "MODO_DUAL_PAGO",
    "No hay operaciones": "SIN_OPERACIONES",
    "IDEMPOTENCY_CONFLICT": "IDEMPOTENCY_CONFLICT",
}


def value_error_to_response(exc: ValueError) -> JSONResponse:
    msg = str(exc)
    codigo = "ERROR_NEGOCIO"
    for fragment, code in _VALUE_ERROR_CODES.items():
        if fragment in msg:
            codigo = code
            break
    status = 409 if codigo == "IDEMPOTENCY_CONFLICT" else 422
    body = ErrorResponse(error=ErrorDetail(codigo=codigo, mensaje=msg))
    return JSONResponse(status_code=status, content=body.model_dump())


def not_found(codigo: str, mensaje: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(codigo=codigo, mensaje=mensaje))
    return JSONResponse(status_code=404, content=body.model_dump())


def bad_request(mensaje: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(codigo="BAD_REQUEST", mensaje=mensaje))
    return JSONResponse(status_code=400, content=body.model_dump())

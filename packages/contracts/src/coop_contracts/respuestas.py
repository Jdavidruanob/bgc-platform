"""Schemas de request y response para la API coop-api."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

# ── Request bodies ────────────────────────────────────────────────────────────


class AporteReqItem(BaseModel):
    socio_id: int
    monto: Annotated[int, Field(gt=0)]


class AportesRequest(BaseModel):
    recibi_de_id: int
    aportes: list[AporteReqItem] = Field(..., min_length=1)


class RetirosRequest(BaseModel):
    socio_id: int
    monto: Annotated[int, Field(gt=0)]


class PagoReqItem(BaseModel):
    socio_id: int
    letra_id: int
    n_cuotas: Annotated[int, Field(ge=0)] = 0
    abono_capital: Annotated[int, Field(ge=0)] = 0


class PagosRequest(BaseModel):
    recibi_de_id: int
    pagos: list[PagoReqItem] = Field(..., min_length=1)


class CombinadosRequest(BaseModel):
    recibi_de_id: int
    aportes: list[AporteReqItem] = Field(default_factory=list)
    pagos: list[PagoReqItem] = Field(default_factory=list)


class CrearCreditoRequest(BaseModel):
    socio_ids: list[int] = Field(..., min_length=1)
    capital: Annotated[int, Field(gt=0)]
    n_cuotas: Annotated[int, Field(gt=0)]
    # Tasa mensual en fracción (0.01 = 1%). Si es None, el API usa el default.
    interes: float | None = None


# ── Respuestas de consulta ────────────────────────────────────────────────────


class HealthOk(BaseModel):
    status: str = "ok"
    version: str


class SocioSearchItem(BaseModel):
    id: int
    nombres: str
    apellidos: str
    nombre_completo: str
    score: float


class SociosSearchResponse(BaseModel):
    socios: list[SocioSearchItem]


class SocioDetalle(BaseModel):
    id: int
    nombres: str
    apellidos: str
    celular: str
    saldo: int
    creditos_activos: int


class CreditoResumen(BaseModel):
    letra_id: int
    capital_original: int
    interes_tasa: float
    n_cuotas_total: int
    fecha_inicio: str
    socios: list[str]


class CreditosResponse(BaseModel):
    creditos: list[CreditoResumen]


class CuotaPendiente(BaseModel):
    nro_cuota: int
    fecha_vencimiento: str
    valor_cuota: int
    interes_mes: int
    cuota_mensual: int
    mora_estimada: int
    estado: str  # "vencida" | "vigente" | "futuro"


class CuotasPendientesResponse(BaseModel):
    letra_id: int
    deuda_total_actual: int
    cuotas_pendientes: list[CuotaPendiente]


class CajaEstado(BaseModel):
    saldo_en_caja: int
    total_admin: int
    porcentaje_mora: float


# ── Respuestas de operación ───────────────────────────────────────────────────


class SocioRef(BaseModel):
    id: int
    nombre_completo: str


class AporteResultItem(BaseModel):
    socio_id: int
    nombre_completo: str
    monto: int
    saldo_anterior: int
    saldo_nuevo: int
    cobro_papeleria: bool


class AportesResponse(BaseModel):
    recibo_id: int
    fecha: str
    recibi_de: SocioRef
    aportes: list[AporteResultItem]
    papeleria_cobrada: int
    saldo_caja_nuevo: int


class RetiroResponse(BaseModel):
    recibo_id: int
    fecha: str
    socio: SocioRef
    monto_retirado: int
    saldo_anterior: int
    saldo_nuevo: int
    saldo_caja_nuevo: int


class PagoResultItem(BaseModel):
    socio_id: int
    nombre_completo: str
    letra_id: int
    cuotas_pagadas: list[int]
    capital_pagado: int
    intereses_pagados: int
    mora_pagada: int
    total_pagado: int
    saldo_capital_antes: int
    saldo_capital_despues: int


class PagosResponse(BaseModel):
    recibo_id: int
    fecha: str
    recibi_de: SocioRef
    pagos: list[PagoResultItem]
    saldo_caja_nuevo: int


class CombinadoResponse(BaseModel):
    recibo_id: int
    fecha: str
    recibi_de: SocioRef
    aportes: list[AporteResultItem]
    pagos: list[PagoResultItem]
    papeleria_cobrada: int
    saldo_caja_nuevo: int


class CuotaAmortizacion(BaseModel):
    nro_cuota: int
    fecha_vencimiento: str
    valor_cuota: int
    interes_mes: int
    cuota_mensual: int
    saldo_capital: int


class CrearCreditoResponse(BaseModel):
    letra_id: int
    fecha: str
    socios: list[SocioRef]
    capital: int
    interes: float
    n_cuotas: int
    saldo_caja_nuevo: int
    tabla_amortizacion: list[CuotaAmortizacion]


# ── Notificaciones ────────────────────────────────────────────────────────────


class NotificacionPendiente(BaseModel):
    id: int
    socio_id: int
    numero_e164: str
    texto: str
    fecha_creacion: str


class NotificacionesPendientesResponse(BaseModel):
    notificaciones: list[NotificacionPendiente]


class PatchNotificacionRequest(BaseModel):
    estado: str  # "enviada" | "fallida"
    error: str | None = None


# ── Errores ───────────────────────────────────────────────────────────────────


class ErrorDetail(BaseModel):
    codigo: str
    mensaje: str
    detalle: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail

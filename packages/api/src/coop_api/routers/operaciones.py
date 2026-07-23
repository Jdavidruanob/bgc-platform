"""Endpoints POST /operaciones/* — todos requieren Idempotency-Key."""

from __future__ import annotations

from typing import Annotated

from coop_contracts.respuestas import (
    AporteResultItem,
    AportesRequest,
    AportesResponse,
    CombinadoResponse,
    CombinadosRequest,
    CrearCreditoRequest,
    CrearCreditoResponse,
    CuotaAmortizacion,
    PagoResultItem,
    PagosRequest,
    PagosResponse,
    RetiroResponse,
    RetirosRequest,
    SocioRef,
)
from coop_core.config.papeleria import PAPELERIA_POR_APORTE, count_cobrables
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.repositories.socios_repo import SociosRepository
from coop_core.services.aporte_service import AporteService
from coop_core.services.combinado_service import CombinadoService
from coop_core.services.credito_service import CreditoService
from coop_core.services.pago_service import PagoService
from coop_core.services.retiro_service import RetiroService
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

import coop_api.idempotency as idem
from coop_api.deps import AuthDep, DbDep
from coop_api.errors import value_error_to_response
from coop_api.recibos import wire as recibos_wire

router = APIRouter(prefix="/operaciones", tags=["operaciones"])

IdempDep = Annotated[str, Header(alias="Idempotency-Key")]

# Límite físico de las plantillas de recibo: máximo 6 aportes y 6 pagos.
_MAX_FILAS_RECIBO = 6


def _require_idem(idempotency_key: IdempDep = None) -> str:  # type: ignore[assignment]
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Header Idempotency-Key requerido")
    return idempotency_key


def _validar_limite(n_aportes: int, n_pagos: int) -> None:
    excede = []
    if n_aportes > _MAX_FILAS_RECIBO:
        excede.append(f"{n_aportes} aportes")
    if n_pagos > _MAX_FILAS_RECIBO:
        excede.append(f"{n_pagos} pagos")
    if excede:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "codigo": "RECIBO_EXCEDE_LIMITE",
                    "mensaje": (
                        f"El recibo soporta máximo {_MAX_FILAS_RECIBO} aportes y "
                        f"{_MAX_FILAS_RECIBO} pagos. Tienes {' y '.join(excede)}. "
                        "Divídelo en varios recibos."
                    ),
                    "detalle": None,
                }
            },
        )


def _get_socio_or_404(socios_repo: SociosRepository, socio_id: int) -> dict[str, object]:
    s = socios_repo.find_by_id(socio_id)
    if s is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "codigo": "SOCIO_NO_ENCONTRADO",
                    "mensaje": f"No existe un socio con ID {socio_id}.",
                    "detalle": None,
                }
            },
        )
    return s


def _socio_ref(s: dict[str, object]) -> SocioRef:
    return SocioRef(id=int(str(s["id"])), nombre_completo=f"{s['nombres']} {s['apellidos']}")


@router.post("/aportes", status_code=201, response_model=None)
def registrar_aportes(
    body: AportesRequest,
    db: DbDep,
    _auth: AuthDep,
    idempotency_key: IdempDep = None,  # type: ignore[assignment]
) -> AportesResponse | JSONResponse:
    idem_key = _require_idem(idempotency_key)
    payload_json = body.model_dump_json()
    try:
        cached = idem.check(db, idem_key, "POST /operaciones/aportes", payload_json)
    except ValueError:
        return value_error_to_response(ValueError("IDEMPOTENCY_CONFLICT"))
    if cached:
        return AportesResponse.model_validate(cached)

    _validar_limite(len(body.aportes), 0)
    socios_repo = SociosRepository(db)
    recibi_de = _get_socio_or_404(socios_repo, body.recibi_de_id)
    aportes_input = []
    for item in body.aportes:
        s = _get_socio_or_404(socios_repo, item.socio_id)
        aportes_input.append({"socio_data": s, "monto": item.monto})

    socio_ids = [item.socio_id for item in body.aportes]
    n_cobrables = count_cobrables(socio_ids)

    svc = AporteService(db, ConfigRepository(db), AuxiliarRepository(db))
    try:
        resultado = svc.register(body.recibi_de_id, aportes_input, n_cobrables)
    except ValueError as exc:
        return value_error_to_response(exc)

    papeleria = PAPELERIA_POR_APORTE * resultado["count_cobrables"]
    aportes_resp = [
        AporteResultItem(
            socio_id=a["socio_id"],
            nombre_completo=f"{a['nombres']} {a['apellidos']}",
            monto=a["monto"],
            saldo_anterior=a["saldo_anterior"],
            saldo_nuevo=a["saldo_nuevo"],
            cobro_papeleria=a["cobro_papeleria"],
        )
        for a in resultado["aportes"]
    ]
    resp = AportesResponse(
        recibo_id=resultado["recibo_id"],
        fecha=resultado["fecha"],
        recibi_de=_socio_ref(recibi_de),
        aportes=aportes_resp,
        papeleria_cobrada=papeleria,
        saldo_caja_nuevo=resultado["nuevo_saldo_caja"],
    )
    recibos_wire.guardar_recibo_aporte(db, resultado, recibi_de)
    idem.store(db, idem_key, "POST /operaciones/aportes", payload_json, resp.model_dump())
    db.commit()
    return resp


@router.post("/retiros", status_code=201, response_model=None)
def registrar_retiro(
    body: RetirosRequest,
    db: DbDep,
    _auth: AuthDep,
    idempotency_key: IdempDep = None,  # type: ignore[assignment]
) -> RetiroResponse | JSONResponse:
    idem_key = _require_idem(idempotency_key)
    payload_json = body.model_dump_json()
    try:
        cached = idem.check(db, idem_key, "POST /operaciones/retiros", payload_json)
    except ValueError:
        return value_error_to_response(ValueError("IDEMPOTENCY_CONFLICT"))
    if cached:
        return RetiroResponse.model_validate(cached)

    socios_repo = SociosRepository(db)
    socio = _get_socio_or_404(socios_repo, body.socio_id)

    svc = RetiroService(db, ConfigRepository(db), AuxiliarRepository(db))
    try:
        resultado = svc.register(socio, body.monto)
    except ValueError as exc:
        return value_error_to_response(exc)

    resp = RetiroResponse(
        recibo_id=resultado["recibo_id"],
        fecha=resultado["fecha"],
        socio=_socio_ref(socio),
        monto_retirado=resultado["monto"],
        saldo_anterior=resultado["saldo_anterior"],
        saldo_nuevo=resultado["saldo_nuevo"],
        saldo_caja_nuevo=resultado["nuevo_saldo_caja"],
    )
    recibos_wire.guardar_recibo_retiro(db, resultado, socio)
    idem.store(db, idem_key, "POST /operaciones/retiros", payload_json, resp.model_dump())
    db.commit()
    return resp


@router.post("/pagos", status_code=201, response_model=None)
def registrar_pagos(
    body: PagosRequest,
    db: DbDep,
    _auth: AuthDep,
    idempotency_key: IdempDep = None,  # type: ignore[assignment]
) -> PagosResponse | JSONResponse:
    idem_key = _require_idem(idempotency_key)
    payload_json = body.model_dump_json()
    try:
        cached = idem.check(db, idem_key, "POST /operaciones/pagos", payload_json)
    except ValueError:
        return value_error_to_response(ValueError("IDEMPOTENCY_CONFLICT"))
    if cached:
        return PagosResponse.model_validate(cached)

    _validar_limite(0, len(body.pagos))
    socios_repo = SociosRepository(db)
    creditos_repo = CreditosRepository(db)
    recibi_de = _get_socio_or_404(socios_repo, body.recibi_de_id)

    pagos_input = []
    for item in body.pagos:
        s = _get_socio_or_404(socios_repo, item.socio_id)
        if creditos_repo.find_by_letra(item.letra_id) is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "codigo": "LETRA_NO_ENCONTRADA",
                        "mensaje": f"No existe un crédito con letra {item.letra_id}.",
                        "detalle": None,
                    }
                },
            )
        pagos_input.append(
            {
                "socio_data": s,
                "letra_id": item.letra_id,
                "n_cuotas": item.n_cuotas,
                "abono_capital": item.abono_capital,
            }
        )

    svc = PagoService(db, LiquidacionesRepository(db), AuxiliarRepository(db), ConfigRepository(db))
    try:
        resultado = svc.register(body.recibi_de_id, pagos_input)
    except ValueError as exc:
        return value_error_to_response(exc)

    pagos_resp = [
        PagoResultItem(
            socio_id=p["socio_id"],
            nombre_completo=f"{p['nombres']} {p['apellidos']}",
            letra_id=p["letra_id"],
            cuotas_pagadas=p.get("cuotas_pagadas", []),
            capital_pagado=p["valor_capital_consolidado"],
            intereses_pagados=p["interes_consolidado"],
            mora_pagada=p["mora_consolidada"],
            total_pagado=p["valor_capital_consolidado"] + p["interes_consolidado"] + p["mora_consolidada"],
            saldo_capital_antes=p["saldo_capital_antes_pago"],
            saldo_capital_despues=p["saldo_capital_despues_pago"],
        )
        for p in resultado["pagos"]
    ]
    resp = PagosResponse(
        recibo_id=resultado["recibo_id"],
        fecha=resultado["fecha"],
        recibi_de=_socio_ref(recibi_de),
        pagos=pagos_resp,
        saldo_caja_nuevo=resultado["nuevo_saldo_caja"],
    )
    recibos_wire.guardar_recibo_pago(db, resultado, recibi_de)
    idem.store(db, idem_key, "POST /operaciones/pagos", payload_json, resp.model_dump())
    db.commit()
    return resp


@router.post("/combinados", status_code=201, response_model=None)
def registrar_combinado(
    body: CombinadosRequest,
    db: DbDep,
    _auth: AuthDep,
    idempotency_key: IdempDep = None,  # type: ignore[assignment]
) -> CombinadoResponse | JSONResponse:
    idem_key = _require_idem(idempotency_key)
    payload_json = body.model_dump_json()
    try:
        cached = idem.check(db, idem_key, "POST /operaciones/combinados", payload_json)
    except ValueError:
        return value_error_to_response(ValueError("IDEMPOTENCY_CONFLICT"))
    if cached:
        return CombinadoResponse.model_validate(cached)

    _validar_limite(len(body.aportes), len(body.pagos))
    socios_repo = SociosRepository(db)
    creditos_repo = CreditosRepository(db)
    recibi_de = _get_socio_or_404(socios_repo, body.recibi_de_id)

    aportes_input = []
    for item in body.aportes:
        s = _get_socio_or_404(socios_repo, item.socio_id)
        aportes_input.append({"socio_data": s, "monto": item.monto})

    pagos_input = []
    for pago_item in body.pagos:
        s = _get_socio_or_404(socios_repo, pago_item.socio_id)
        if creditos_repo.find_by_letra(pago_item.letra_id) is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "codigo": "LETRA_NO_ENCONTRADA",
                        "mensaje": f"No existe un crédito con letra {pago_item.letra_id}.",
                        "detalle": None,
                    }
                },
            )
        pagos_input.append(
            {
                "socio_data": s,
                "letra_id": pago_item.letra_id,
                "n_cuotas": pago_item.n_cuotas,
                "abono_capital": pago_item.abono_capital,
            }
        )

    n_cobrables = count_cobrables([aporte_item.socio_id for aporte_item in body.aportes])
    svc = CombinadoService(db, LiquidacionesRepository(db), AuxiliarRepository(db), ConfigRepository(db))
    try:
        resultado = svc.register(body.recibi_de_id, aportes_input, pagos_input, n_cobrables)
    except ValueError as exc:
        return value_error_to_response(exc)

    papeleria = PAPELERIA_POR_APORTE * n_cobrables
    aportes_resp = [
        AporteResultItem(
            socio_id=a["socio_id"],
            nombre_completo=f"{a['nombres']} {a['apellidos']}",
            monto=a["monto"],
            saldo_anterior=a["saldo_anterior"],
            saldo_nuevo=a["saldo_nuevo"],
            cobro_papeleria=a["cobro_papeleria"],
        )
        for a in resultado["aportes"]
    ]
    pagos_resp = [
        PagoResultItem(
            socio_id=p["socio_id"],
            nombre_completo=f"{p['nombres']} {p['apellidos']}",
            letra_id=p["letra_id"],
            cuotas_pagadas=p.get("cuotas_pagadas", []),
            capital_pagado=p["valor_capital_consolidado"],
            intereses_pagados=p["interes_consolidado"],
            mora_pagada=p["mora_consolidada"],
            total_pagado=p["valor_capital_consolidado"] + p["interes_consolidado"] + p["mora_consolidada"],
            saldo_capital_antes=p["saldo_capital_antes_pago"],
            saldo_capital_despues=p["saldo_capital_despues_pago"],
        )
        for p in resultado["pagos"]
    ]
    resp = CombinadoResponse(
        recibo_id=resultado["recibo_id"],
        fecha=resultado["fecha"],
        recibi_de=_socio_ref(recibi_de),
        aportes=aportes_resp,
        pagos=pagos_resp,
        papeleria_cobrada=papeleria,
        saldo_caja_nuevo=resultado["nuevo_saldo_caja"],
    )
    recibos_wire.guardar_recibo_combinado(db, resultado, recibi_de, n_cobrables)
    idem.store(db, idem_key, "POST /operaciones/combinados", payload_json, resp.model_dump())
    db.commit()
    return resp


_INTERES_DEFAULT = 0.01  # 1% mensual, mismo default que el BGC-software original


@router.post("/creditos", status_code=201, response_model=None)
def crear_credito(
    body: CrearCreditoRequest,
    db: DbDep,
    _auth: AuthDep,
    idempotency_key: IdempDep = None,  # type: ignore[assignment]
) -> CrearCreditoResponse | JSONResponse:
    idem_key = _require_idem(idempotency_key)
    payload_json = body.model_dump_json()
    try:
        cached = idem.check(db, idem_key, "POST /operaciones/creditos", payload_json)
    except ValueError:
        return value_error_to_response(ValueError("IDEMPOTENCY_CONFLICT"))
    if cached:
        return CrearCreditoResponse.model_validate(cached)

    socios_repo = SociosRepository(db)
    socios_data = [_get_socio_or_404(socios_repo, sid) for sid in body.socio_ids]
    interes = body.interes if body.interes is not None else _INTERES_DEFAULT

    svc = CreditoService(
        db,
        CreditosRepository(db),
        LiquidacionesRepository(db),
        AuxiliarRepository(db),
        ConfigRepository(db),
    )
    try:
        resultado = svc.create(body.socio_ids, body.capital, interes, body.n_cuotas, socios_data)
    except ValueError as exc:
        return value_error_to_response(exc)

    resp = CrearCreditoResponse(
        letra_id=resultado["letra_id"],
        fecha=resultado["fecha"],
        socios=[
            SocioRef(id=int(s["id"]), nombre_completo=f"{s['nombres']} {s['apellidos']}")
            for s in resultado["socios"]
        ],
        capital=resultado["capital"],
        interes=resultado["interes"],
        n_cuotas=resultado["n_cuotas"],
        saldo_caja_nuevo=resultado["nuevo_saldo_caja"],
        tabla_amortizacion=[CuotaAmortizacion(**c) for c in resultado["tabla_amortizacion"]],
    )
    # CreditoService.create ya hizo commit del crédito. La liquidación y la clave
    # de idempotencia se guardan en transacciones posteriores.
    recibos_wire.guardar_liquidacion_credito(db, resultado)
    idem.store(db, idem_key, "POST /operaciones/creditos", payload_json, resp.model_dump())
    db.commit()
    return resp

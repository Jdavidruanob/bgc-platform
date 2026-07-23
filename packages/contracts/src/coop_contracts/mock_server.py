"""Mock server de coop-api. Levanta en puerto 8001.

Uso:
    uv run --package coop-contracts python -m coop_contracts.mock_server
"""

from __future__ import annotations

import difflib
import os
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response

from coop_contracts.mock_data import get_initial_state, make_nombre_completo
from coop_contracts.respuestas import (
    AporteResultItem,
    AportesRequest,
    AportesResponse,
    CajaEstado,
    CombinadoResponse,
    CombinadosRequest,
    CrearCreditoRequest,
    CrearCreditoResponse,
    CreditoDetalle,
    CreditoResumen,
    CreditoSocio,
    CreditosResponse,
    CuotaAmortizacion,
    CuotaPendiente,
    CuotasPendientesResponse,
    ErrorDetail,
    ErrorResponse,
    FamiliaResponse,
    HealthOk,
    MiembroFamilia,
    NotificacionesPendientesResponse,
    NotificacionPendiente,
    PagoResultItem,
    PagosRequest,
    PagosResponse,
    PatchNotificacionRequest,
    RetiroResponse,
    RetirosRequest,
    SocioDetalle,
    SocioRef,
    SocioSearchItem,
    SociosSearchResponse,
)

app = FastAPI(title="coop-api (mock)", version="0.1.0")

# Estado mutable en memoria — se reinicia via POST /test/reset
_state: dict = get_initial_state()

_MOCK_TOKEN = os.environ.get("API_SECRET_TOKEN", "mock-secret")
_PAPELERIA = 3000


# ── Helpers ───────────────────────────────────────────────────────────────────


def _error(codigo: str, mensaje: str, status_code: int, detalle: Any = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(codigo=codigo, mensaje=mensaje, detalle=detalle))
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _find_socio(socio_id: int) -> dict:
    for s in _state["socios"]:
        if s["id"] == socio_id:
            return s
    raise HTTPException(
        status_code=404,
        detail=ErrorResponse(
            error=ErrorDetail(
                codigo="SOCIO_NO_ENCONTRADO",
                mensaje=f"No existe un socio con ID {socio_id}.",
            )
        ).model_dump(),
    )


def _find_credito(letra_id: int) -> dict:
    for c in _state["creditos"]:
        if c["letra_id"] == letra_id:
            return c
    raise HTTPException(
        status_code=404,
        detail=ErrorResponse(
            error=ErrorDetail(
                codigo="LETRA_NO_ENCONTRADA",
                mensaje=f"No existe un crédito con letra {letra_id}.",
            )
        ).model_dump(),
    )


def _fuzzy_score(query: str, name: str) -> float:
    q = query.lower().strip()
    n = name.lower()
    if q == n:
        return 1.0
    if q in n:
        return 0.90
    return difflib.SequenceMatcher(None, q, n).ratio()


def _next_recibo() -> int:
    rid = _state["next_recibo_id"]
    _state["next_recibo_id"] += 1
    return rid


def _today() -> str:
    return date.today().isoformat()


# ── Auth dependency ───────────────────────────────────────────────────────────


def _require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
    if authorization != f"Bearer {_MOCK_TOKEN}":
        raise HTTPException(status_code=401, detail="Token ausente o inválido")


def _require_idempotency(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Header Idempotency-Key requerido")
    return idempotency_key


AuthDep = Annotated[None, Depends(_require_auth)]
IdempDep = Annotated[str, Depends(_require_idempotency)]


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> HealthOk:
    return HealthOk(version="0.1.0")


# ── Socios ────────────────────────────────────────────────────────────────────


@app.get("/socios/lista")
def listar_todos_socios(_auth: AuthDep = None) -> SociosSearchResponse:
    items = [
        SocioSearchItem(
            id=s["id"],
            nombres=s["nombres"],
            apellidos=s["apellidos"],
            nombre_completo=make_nombre_completo(s),
            score=1.0,
        )
        for s in _state["socios"]
    ]
    items.sort(key=lambda x: x.nombre_completo)
    return SociosSearchResponse(socios=items)


@app.get("/socios")
def buscar_socios(q: str = "", limit: int = 10, _auth: AuthDep = None) -> SociosSearchResponse:
    if not q.strip():
        raise HTTPException(status_code=400, detail="El parámetro 'q' es requerido")
    resultados: list[SocioSearchItem] = []
    for s in _state["socios"]:
        nombre_completo = make_nombre_completo(s)
        score = _fuzzy_score(q, nombre_completo)
        if score >= 0.5:
            resultados.append(
                SocioSearchItem(
                    id=s["id"],
                    nombres=s["nombres"],
                    apellidos=s["apellidos"],
                    nombre_completo=nombre_completo,
                    score=round(score, 4),
                )
            )
    resultados.sort(key=lambda x: x.score, reverse=True)
    return SociosSearchResponse(socios=resultados[:limit])


@app.get("/socios/{socio_id}")
def get_socio(socio_id: int, _auth: AuthDep = None) -> SocioDetalle:
    s = _find_socio(socio_id)
    return SocioDetalle(
        id=s["id"],
        nombres=s["nombres"],
        apellidos=s["apellidos"],
        celular=s["celular"],
        saldo=s["saldo"],
        creditos_activos=s["creditos_activos"],
    )


@app.get("/socios/{socio_id}/familia")
def get_familia(socio_id: int, _auth: AuthDep = None) -> FamiliaResponse:
    socio = _find_socio(socio_id)
    familia_id = socio.get("familia_id")
    if familia_id is None:
        miembros_raw = [socio]
    else:
        miembros_raw = [s for s in _state["socios"] if s.get("familia_id") == familia_id]
    miembros = [
        MiembroFamilia(id=s["id"], nombre_completo=make_nombre_completo(s), saldo=s["saldo"])
        for s in miembros_raw
    ]
    return FamiliaResponse(socio_id=socio_id, miembros=miembros)


@app.get("/socios/{socio_id}/creditos")
def get_creditos_socio(socio_id: int, _auth: AuthDep = None) -> CreditosResponse:
    _find_socio(socio_id)
    creditos = [
        CreditoResumen(
            letra_id=c["letra_id"],
            capital_original=c["capital_original"],
            interes_tasa=c["interes_tasa"],
            n_cuotas_total=c["n_cuotas_total"],
            fecha_inicio=c["fecha_inicio"],
            socios=c["socios_nombres"],
        )
        for c in _state["creditos"]
        if socio_id in c["socio_ids"]
    ]
    return CreditosResponse(creditos=creditos)


@app.get("/creditos/{letra_id}")
def get_credito(letra_id: int, _auth: AuthDep = None) -> CreditoDetalle:
    c = _find_credito(letra_id)
    socios = []
    for sid in c["socio_ids"]:
        s = _find_socio(sid)
        socios.append(CreditoSocio(id=sid, nombre_completo=make_nombre_completo(s)))
    return CreditoDetalle(
        letra_id=letra_id,
        capital=c["capital_original"],
        interes_tasa=c["interes_tasa"],
        n_cuotas_total=c["n_cuotas_total"],
        fecha_inicio=c["fecha_inicio"],
        socios=socios,
    )


@app.get("/creditos/{letra_id}/cuotas-pendientes")
def get_cuotas_pendientes(letra_id: int, _auth: AuthDep = None) -> CuotasPendientesResponse:
    c = _find_credito(letra_id)
    deuda_total = sum(q["cuota_mensual"] + q["mora_estimada"] for q in c["cuotas_pendientes"])
    cuotas = [CuotaPendiente(**q) for q in c["cuotas_pendientes"]]
    return CuotasPendientesResponse(
        letra_id=letra_id,
        deuda_total_actual=deuda_total,
        cuotas_pendientes=cuotas,
    )


@app.get("/creditos/{letra_id}/liquidacion-actual/pdf")
def get_liquidacion_actual(letra_id: int, _auth: AuthDep = None) -> Response:
    _find_credito(letra_id)
    # PDF ficticio: mínimo válido para que el bot pueda reenviarlo en tests.
    contenido = b"%PDF-1.4 mock liquidacion actual letra " + str(letra_id).encode()
    return Response(content=contenido, media_type="application/pdf")


# ── Caja ──────────────────────────────────────────────────────────────────────


@app.get("/caja")
def get_caja(_auth: AuthDep = None) -> CajaEstado:
    caja = _state["caja"]
    papeleria = caja["total_admin"]
    mora_acumulada = caja.get("mora_acumulada", 0)
    return CajaEstado(
        saldo_en_caja=caja["saldo_en_caja"],
        total_admin=papeleria,
        porcentaje_mora=caja["porcentaje_mora"],
        papeleria=papeleria,
        mora_acumulada=mora_acumulada,
        administracion_total=papeleria + mora_acumulada,
    )


# ── Operaciones ───────────────────────────────────────────────────────────────


def _check_idempotency(key: str, payload_hash: int) -> dict | None:
    if key in _state["idempotency_keys"]:
        stored = _state["idempotency_keys"][key]
        if stored["payload_hash"] != payload_hash:
            raise HTTPException(
                status_code=409,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        codigo="IDEMPOTENCY_CONFLICT",
                        mensaje="La clave de idempotencia ya fue usada con un payload diferente.",
                    )
                ).model_dump(),
            )
        return stored["result"]
    return None


def _store_idempotency(key: str, payload_hash: int, result: dict) -> None:
    _state["idempotency_keys"][key] = {"payload_hash": payload_hash, "result": result}


@app.post("/operaciones/aportes", status_code=201)
def registrar_aportes(
    body: AportesRequest,
    _auth: AuthDep = None,
    idem_key: IdempDep = None,
) -> AportesResponse:
    payload_hash = hash(body.model_dump_json())
    cached = _check_idempotency(idem_key, payload_hash)
    if cached:
        return AportesResponse(**cached)

    recibi_de = _find_socio(body.recibi_de_id)
    fecha = _today()
    recibo_id = _next_recibo()
    papeleria_total = 0
    aportes_result: list[AporteResultItem] = []

    for item in body.aportes:
        s = _find_socio(item.socio_id)
        cobra = item.socio_id != body.recibi_de_id  # mock simplificado: exento solo el que entrega
        saldo_ant = s["saldo"]
        s["saldo"] += item.monto
        if cobra:
            papeleria_total += _PAPELERIA
            _state["caja"]["total_admin"] += _PAPELERIA
        _state["caja"]["saldo_en_caja"] += item.monto
        aportes_result.append(
            AporteResultItem(
                socio_id=s["id"],
                nombre_completo=make_nombre_completo(s),
                monto=item.monto,
                saldo_anterior=saldo_ant,
                saldo_nuevo=s["saldo"],
                cobro_papeleria=cobra,
            )
        )

    resp = AportesResponse(
        recibo_id=recibo_id,
        fecha=fecha,
        recibi_de=SocioRef(id=recibi_de["id"], nombre_completo=make_nombre_completo(recibi_de)),
        aportes=aportes_result,
        papeleria_cobrada=papeleria_total,
        saldo_caja_nuevo=_state["caja"]["saldo_en_caja"],
    )
    _store_idempotency(idem_key, payload_hash, resp.model_dump())
    return resp


@app.post("/operaciones/retiros", status_code=201)
def registrar_retiro(
    body: RetirosRequest,
    _auth: AuthDep = None,
    idem_key: IdempDep = None,
) -> RetiroResponse:
    payload_hash = hash(body.model_dump_json())
    cached = _check_idempotency(idem_key, payload_hash)
    if cached:
        return RetiroResponse(**cached)

    s = _find_socio(body.socio_id)
    if s["saldo"] < body.monto:
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error=ErrorDetail(
                    codigo="SALDO_INSUFICIENTE",
                    mensaje="El socio no tiene saldo suficiente para este retiro.",
                )
            ).model_dump(),
        )

    saldo_ant = s["saldo"]
    s["saldo"] -= body.monto
    _state["caja"]["saldo_en_caja"] -= body.monto
    recibo_id = _next_recibo()

    resp = RetiroResponse(
        recibo_id=recibo_id,
        fecha=_today(),
        socio=SocioRef(id=s["id"], nombre_completo=make_nombre_completo(s)),
        monto_retirado=body.monto,
        saldo_anterior=saldo_ant,
        saldo_nuevo=s["saldo"],
        saldo_caja_nuevo=_state["caja"]["saldo_en_caja"],
    )
    _store_idempotency(idem_key, payload_hash, resp.model_dump())
    return resp


@app.post("/operaciones/pagos", status_code=201)
def registrar_pagos(
    body: PagosRequest,
    _auth: AuthDep = None,
    idem_key: IdempDep = None,
) -> PagosResponse:
    payload_hash = hash(body.model_dump_json())
    cached = _check_idempotency(idem_key, payload_hash)
    if cached:
        return PagosResponse(**cached)

    recibi_de = _find_socio(body.recibi_de_id)
    recibo_id = _next_recibo()
    pagos_result: list[PagoResultItem] = []
    total_ingreso = 0

    for item in body.pagos:
        s = _find_socio(item.socio_id)
        credito = _find_credito(item.letra_id)

        cuotas_pend = credito["cuotas_pendientes"]
        if not cuotas_pend:
            raise HTTPException(
                status_code=422,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        codigo="CUOTAS_INSUFICIENTES",
                        mensaje=f"No hay cuotas pendientes en la letra {item.letra_id}.",
                    )
                ).model_dump(),
            )

        cuotas_a_pagar = cuotas_pend[: item.n_cuotas] if item.n_cuotas > 0 else cuotas_pend[:1]
        capital_pagado = sum(q["valor_cuota"] for q in cuotas_a_pagar)
        intereses = sum(q["interes_mes"] for q in cuotas_a_pagar)
        mora = sum(q["mora_estimada"] for q in cuotas_a_pagar)
        total_cuotas = sum(q["cuota_mensual"] for q in cuotas_a_pagar)
        nros = [q["nro_cuota"] for q in cuotas_a_pagar]

        saldo_antes = credito["saldo_capital"]
        credito["saldo_capital"] -= capital_pagado
        credito["cuotas_pendientes"] = cuotas_pend[len(cuotas_a_pagar) :]
        total_ingreso += total_cuotas + mora

        pagos_result.append(
            PagoResultItem(
                socio_id=s["id"],
                nombre_completo=make_nombre_completo(s),
                letra_id=item.letra_id,
                cuotas_pagadas=nros,
                capital_pagado=capital_pagado,
                intereses_pagados=intereses,
                mora_pagada=mora,
                total_pagado=total_cuotas + mora,
                saldo_capital_antes=saldo_antes,
                saldo_capital_despues=credito["saldo_capital"],
            )
        )

    _state["caja"]["saldo_en_caja"] += total_ingreso

    resp = PagosResponse(
        recibo_id=recibo_id,
        fecha=_today(),
        recibi_de=SocioRef(id=recibi_de["id"], nombre_completo=make_nombre_completo(recibi_de)),
        pagos=pagos_result,
        saldo_caja_nuevo=_state["caja"]["saldo_en_caja"],
    )
    _store_idempotency(idem_key, payload_hash, resp.model_dump())
    return resp


@app.post("/operaciones/combinados", status_code=201)
def registrar_combinado(
    body: CombinadosRequest,
    _auth: AuthDep = None,
    idem_key: IdempDep = None,
) -> CombinadoResponse:
    payload_hash = hash(body.model_dump_json())
    cached = _check_idempotency(idem_key, payload_hash)
    if cached:
        return CombinadoResponse(**cached)

    # Reutilizar lógica de aportes
    AportesRequest(recibi_de_id=body.recibi_de_id, aportes=body.aportes)
    AportesRequest(recibi_de_id=body.recibi_de_id, aportes=body.aportes)
    # Llamar internamente sin idempotencia (ya la manejamos arriba)
    recibi_de = _find_socio(body.recibi_de_id)
    recibo_id = _next_recibo()
    papeleria_total = 0
    aportes_result: list[AporteResultItem] = []

    for item in body.aportes:
        s = _find_socio(item.socio_id)
        cobra = item.socio_id != body.recibi_de_id
        saldo_ant = s["saldo"]
        s["saldo"] += item.monto
        if cobra:
            papeleria_total += _PAPELERIA
            _state["caja"]["total_admin"] += _PAPELERIA
        _state["caja"]["saldo_en_caja"] += item.monto
        aportes_result.append(
            AporteResultItem(
                socio_id=s["id"],
                nombre_completo=make_nombre_completo(s),
                monto=item.monto,
                saldo_anterior=saldo_ant,
                saldo_nuevo=s["saldo"],
                cobro_papeleria=cobra,
            )
        )

    pagos_result: list[PagoResultItem] = []
    total_pagos = 0
    for item in body.pagos:
        s = _find_socio(item.socio_id)
        credito = _find_credito(item.letra_id)
        cuotas_pend = credito["cuotas_pendientes"]
        cuotas_a_pagar = cuotas_pend[: item.n_cuotas] if item.n_cuotas > 0 else cuotas_pend[:1]
        capital_pagado = sum(q["valor_cuota"] for q in cuotas_a_pagar)
        intereses = sum(q["interes_mes"] for q in cuotas_a_pagar)
        mora = sum(q["mora_estimada"] for q in cuotas_a_pagar)
        total_c = sum(q["cuota_mensual"] for q in cuotas_a_pagar)
        nros = [q["nro_cuota"] for q in cuotas_a_pagar]
        saldo_antes = credito["saldo_capital"]
        credito["saldo_capital"] -= capital_pagado
        credito["cuotas_pendientes"] = cuotas_pend[len(cuotas_a_pagar) :]
        total_pagos += total_c + mora
        pagos_result.append(
            PagoResultItem(
                socio_id=s["id"],
                nombre_completo=make_nombre_completo(s),
                letra_id=item.letra_id,
                cuotas_pagadas=nros,
                capital_pagado=capital_pagado,
                intereses_pagados=intereses,
                mora_pagada=mora,
                total_pagado=total_c + mora,
                saldo_capital_antes=saldo_antes,
                saldo_capital_despues=credito["saldo_capital"],
            )
        )

    _state["caja"]["saldo_en_caja"] += total_pagos

    resp = CombinadoResponse(
        recibo_id=recibo_id,
        fecha=_today(),
        recibi_de=SocioRef(id=recibi_de["id"], nombre_completo=make_nombre_completo(recibi_de)),
        aportes=aportes_result,
        pagos=pagos_result,
        papeleria_cobrada=papeleria_total,
        saldo_caja_nuevo=_state["caja"]["saldo_en_caja"],
    )
    _store_idempotency(idem_key, payload_hash, resp.model_dump())
    return resp


@app.post("/operaciones/creditos", status_code=201)
def crear_credito(
    body: CrearCreditoRequest,
    _auth: AuthDep = None,
    idem_key: IdempDep = None,
) -> CrearCreditoResponse:
    payload_hash = hash(body.model_dump_json())
    cached = _check_idempotency(idem_key, payload_hash)
    if cached:
        return CrearCreditoResponse(**cached)

    socios = [_find_socio(sid) for sid in body.socio_ids]
    interes = body.interes if body.interes is not None else 0.01
    letra_id = 900 + len(_state["creditos"]) + 1

    # Amortización simplificada del mock (cuota lineal + interés sobre saldo).
    cuota_base = body.capital // body.n_cuotas
    tabla: list[CuotaAmortizacion] = []
    saldo = body.capital
    for i in range(body.n_cuotas):
        nro = i + 1
        cap = body.capital - cuota_base * (body.n_cuotas - 1) if nro == body.n_cuotas else cuota_base
        interes_mes = round(saldo * interes)
        saldo = max(saldo - cap, 0)
        tabla.append(
            CuotaAmortizacion(
                nro_cuota=nro,
                fecha_vencimiento=_today(),
                valor_cuota=cap,
                interes_mes=interes_mes,
                cuota_mensual=cap + interes_mes,
                saldo_capital=saldo,
            )
        )

    _state["caja"]["saldo_en_caja"] -= body.capital
    _state["creditos"].append(
        {"letra": letra_id, "capital": body.capital, "interes": interes, "no_cuotas": body.n_cuotas}
    )

    resp = CrearCreditoResponse(
        letra_id=letra_id,
        fecha=_today(),
        socios=[SocioRef(id=s["id"], nombre_completo=make_nombre_completo(s)) for s in socios],
        capital=body.capital,
        interes=interes,
        n_cuotas=body.n_cuotas,
        saldo_caja_nuevo=_state["caja"]["saldo_en_caja"],
        tabla_amortizacion=tabla,
    )
    _store_idempotency(idem_key, payload_hash, resp.model_dump())
    return resp


# ── Notificaciones ────────────────────────────────────────────────────────────


@app.get("/notificaciones/pendientes")
def get_notificaciones_pendientes(_auth: AuthDep = None) -> NotificacionesPendientesResponse:
    pendientes = [NotificacionPendiente(**n) for n in _state["notificaciones"] if n["estado"] == "pendiente"]
    return NotificacionesPendientesResponse(notificaciones=pendientes)


@app.patch("/notificaciones/{notif_id}", status_code=200)
def patch_notificacion(
    notif_id: int,
    body: PatchNotificacionRequest,
    _auth: AuthDep = None,
) -> dict:
    for n in _state["notificaciones"]:
        if n["id"] == notif_id:
            n["estado"] = body.estado
            if body.error:
                n["error"] = body.error
            return {"id": notif_id, "estado": body.estado}
    raise HTTPException(status_code=404, detail=f"Notificación {notif_id} no encontrada")


# ── Test utilities (solo para entorno de testing) ─────────────────────────────


@app.post("/test/reset", status_code=200, include_in_schema=False)
def reset_state() -> dict:
    """Reinicia el estado en memoria al inicial. Solo para tests."""
    global _state
    _state = get_initial_state()
    return {"reset": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("coop_contracts.mock_server:app", host="0.0.0.0", port=8001, reload=False)

"""Encola notificaciones de WhatsApp a los socios cuando se registra una
operación. Se llama desde cada endpoint de `operaciones.py` justo antes de
`db.commit()`, en la misma transacción — si la operación falla, no queda una
notificación huérfana.

Nunca bloquea ni falla la operación: si un socio no tiene número derivable, se
salta en silencio (no todos los socios tienen WhatsApp registrado aún).
"""

from __future__ import annotations

from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.notificaciones_repo import NotificacionesRepository
from coop_core.repositories.socios_repo import SociosRepository
from coop_core.utils.formato import format_miles_colombian_int
from coop_core.utils.telefono import derivar_whatsapp_e164

_FIRMA = "— Cooperativa BGC"


def _monto(valor: int) -> str:
    return f"${format_miles_colombian_int(valor)}"


def _numero_de(socio: dict[str, Any]) -> str | None:
    return derivar_whatsapp_e164(
        socio.get("whatsapp_e164") if isinstance(socio, dict) else None,
        socio.get("celular") if isinstance(socio, dict) else None,
    )


def _socio_por_id(db: DbConnection, socio_id: int) -> dict[str, Any] | None:
    return SociosRepository(db).find_by_id(socio_id)


def _encolar(
    repo: NotificacionesRepository,
    socio_id: int,
    socio: dict[str, Any] | None,
    texto: str,
    documento_tipo: str | None = None,
    documento_id: int | None = None,
) -> None:
    if socio is None:
        return
    numero = _numero_de(socio)
    if numero is None:
        return
    repo.create(socio_id, numero, texto, documento_tipo, documento_id)


def notificar_aportes(db: DbConnection, resultado: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    recibo_id = int(resultado["recibo_id"])
    for a in resultado["aportes"]:
        socio_id = int(a["socio_id"])
        texto = (
            f"Hola {a['nombres']}, registramos tu aporte de {_monto(int(a['monto']))}. "
            f"Tu nuevo saldo es {_monto(int(a['saldo_nuevo']))}. {_FIRMA}"
        )
        _encolar(repo, socio_id, _socio_por_id(db, socio_id), texto, "recibo", recibo_id)


def notificar_retiro(db: DbConnection, resultado: dict[str, Any], socio: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    recibo_id = int(resultado["recibo_id"])
    texto = (
        f"Hola {socio['nombres']}, registramos tu retiro de {_monto(int(resultado['monto']))}. "
        f"Tu nuevo saldo es {_monto(int(resultado['saldo_nuevo']))}. {_FIRMA}"
    )
    _encolar(repo, int(socio["id"]), socio, texto, "recibo", recibo_id)


def _texto_pago(p: dict[str, Any]) -> str:
    letra_id = int(p["letra_id"])
    cuotas = p.get("cuotas_pagadas") or []
    total = (
        int(p["valor_capital_consolidado"])
        + int(p["interes_consolidado"])
        + int(p.get("mora_consolidada", 0))
    )
    if cuotas:
        detalle = f"{len(cuotas)} cuota(s)" if len(cuotas) > 1 else "1 cuota"
    else:
        detalle = "un abono a capital"
    return (
        f"Hola {p['nombres']}, registramos el pago de {detalle} de tu crédito "
        f"(letra {letra_id}) por {_monto(total)}. {_FIRMA}"
    )


def notificar_pagos(db: DbConnection, resultado: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    recibo_id = int(resultado["recibo_id"])
    for p in resultado["pagos"]:
        socio_id = int(p["socio_id"])
        _encolar(repo, socio_id, _socio_por_id(db, socio_id), _texto_pago(p), "recibo", recibo_id)


def notificar_combinado(db: DbConnection, resultado: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    recibo_id = int(resultado["recibo_id"])
    for a in resultado["aportes"]:
        socio_id = int(a["socio_id"])
        texto = (
            f"Hola {a['nombres']}, registramos tu aporte de {_monto(int(a['monto']))}. "
            f"Tu nuevo saldo es {_monto(int(a['saldo_nuevo']))}. {_FIRMA}"
        )
        _encolar(repo, socio_id, _socio_por_id(db, socio_id), texto, "recibo", recibo_id)
    for p in resultado["pagos"]:
        socio_id = int(p["socio_id"])
        _encolar(repo, socio_id, _socio_por_id(db, socio_id), _texto_pago(p), "recibo", recibo_id)


def notificar_credito_nuevo(db: DbConnection, resultado: dict[str, Any]) -> None:
    """El crédito no genera fila en `recibos` (solo créditos/liquidaciones), así
    que esta notificación va sin documento adjunto: solo texto."""
    repo = NotificacionesRepository(db)
    letra_id = int(resultado["letra_id"])
    for s in resultado["socios"]:
        socio_id = int(s["id"])
        texto = (
            f"Hola {s['nombres']}, tu crédito por {_monto(int(resultado['capital']))} a "
            f"{int(resultado['n_cuotas'])} cuotas fue aprobado (letra {letra_id}). {_FIRMA}"
        )
        _encolar(repo, socio_id, _socio_por_id(db, socio_id), texto)

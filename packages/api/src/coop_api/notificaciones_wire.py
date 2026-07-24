"""Encola notificaciones de WhatsApp a los socios cuando se registra una
operación. Se llama desde cada endpoint de `operaciones.py` justo antes de
`db.commit()`, en la misma transacción — si la operación falla, no queda una
notificación huérfana.

Cada notificación guarda dos versiones del mismo aviso:

- `detalle`: el resumen de la operación en UNA sola línea, que viaja como
  variable de la plantilla de Meta (las variables no admiten saltos de línea
  ni tabulaciones).
- `texto`: el mensaje completo ya redactado, que se usa cuando se envía como
  texto libre o cuando se cae al fallback wa.me.

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

_FIRMA = "Cooperativa BGC\n¡Gracias por tu confianza!"
_CIERRE_COMPROBANTE = "Te adjuntamos el comprobante de la operación."
_CIERRE_LIQUIDACION = "Te adjuntamos la liquidación con el plan de pagos."


def _monto(valor: int) -> str:
    return f"${format_miles_colombian_int(valor)}"


def _primer_nombre(nombres: Any) -> str:
    """'Pedro Antonio' → 'Pedro'. El saludo suena más natural con un solo
    nombre; si viene vacío se saluda sin nombre."""
    partes = str(nombres or "").strip().split()
    return partes[0].capitalize() if partes else ""


def _mensaje(nombres: Any, detalle: str, cierre: str) -> str:
    """Arma el mensaje completo a partir del mismo `detalle` que viaja como
    variable de la plantilla, para que ambas versiones digan lo mismo."""
    nombre = _primer_nombre(nombres)
    saludo = f"Hola {nombre} 👋" if nombre else "Hola 👋"
    return f"{saludo}\n\n{detalle}.\n\n{cierre}\n\n{_FIRMA}"


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
    detalle: str,
    cierre: str,
    documento_tipo: str | None = None,
    documento_id: int | None = None,
) -> None:
    if socio is None:
        return
    numero = _numero_de(socio)
    if numero is None:
        return
    texto = _mensaje(socio.get("nombres"), detalle, cierre)
    repo.create(socio_id, numero, texto, documento_tipo, documento_id, detalle)


def _detalle_aporte(a: dict[str, Any]) -> str:
    return (
        f"Registramos tu aporte de {_monto(int(a['monto']))} "
        f"y tu nuevo saldo es {_monto(int(a['saldo_nuevo']))}"
    )


def _detalle_pago(p: dict[str, Any]) -> str:
    letra_id = int(p["letra_id"])
    cuotas = p.get("cuotas_pagadas") or []
    total = (
        int(p["valor_capital_consolidado"])
        + int(p["interes_consolidado"])
        + int(p.get("mora_consolidada", 0))
    )
    if not cuotas:
        detalle = "un abono a capital"
    elif len(cuotas) > 1:
        detalle = f"{len(cuotas)} cuotas"
    else:
        detalle = "1 cuota"
    return f"Registramos el pago de {detalle} de tu crédito (letra {letra_id}) por {_monto(total)}"


def notificar_aportes(db: DbConnection, resultado: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    recibo_id = int(resultado["recibo_id"])
    for a in resultado["aportes"]:
        socio_id = int(a["socio_id"])
        _encolar(
            repo,
            socio_id,
            _socio_por_id(db, socio_id),
            _detalle_aporte(a),
            _CIERRE_COMPROBANTE,
            "recibo",
            recibo_id,
        )


def notificar_retiro(db: DbConnection, resultado: dict[str, Any], socio: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    detalle = (
        f"Registramos tu retiro de {_monto(int(resultado['monto']))} "
        f"y tu nuevo saldo es {_monto(int(resultado['saldo_nuevo']))}"
    )
    _encolar(
        repo,
        int(socio["id"]),
        socio,
        detalle,
        _CIERRE_COMPROBANTE,
        "recibo",
        int(resultado["recibo_id"]),
    )


def notificar_pagos(db: DbConnection, resultado: dict[str, Any]) -> None:
    repo = NotificacionesRepository(db)
    recibo_id = int(resultado["recibo_id"])
    for p in resultado["pagos"]:
        socio_id = int(p["socio_id"])
        _encolar(
            repo,
            socio_id,
            _socio_por_id(db, socio_id),
            _detalle_pago(p),
            _CIERRE_COMPROBANTE,
            "recibo",
            recibo_id,
        )


def notificar_combinado(db: DbConnection, resultado: dict[str, Any]) -> None:
    notificar_aportes(db, resultado)
    notificar_pagos(db, resultado)


def notificar_credito_nuevo(db: DbConnection, resultado: dict[str, Any]) -> None:
    """El crédito no genera fila en `recibos`, pero sí una liquidación: se
    adjunta esa (documento_tipo='liquidacion', documento_id=letra_id)."""
    repo = NotificacionesRepository(db)
    letra_id = int(resultado["letra_id"])
    detalle = (
        f"¡Buenas noticias! Tu crédito por {_monto(int(resultado['capital']))} "
        f"a {int(resultado['n_cuotas'])} cuotas fue aprobado (letra {letra_id})"
    )
    for s in resultado["socios"]:
        socio_id = int(s["id"])
        _encolar(
            repo,
            socio_id,
            _socio_por_id(db, socio_id),
            detalle,
            _CIERRE_LIQUIDACION,
            "liquidacion",
            letra_id,
        )

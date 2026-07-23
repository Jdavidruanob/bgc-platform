"""Construcción del texto de confirmación mostrado al operador. Funciones puras, sin I/O.

Solo maneja retiro y crear crédito (que van por su cuenta). Los aportes, pagos y
combinado usan `_resumen_plan` en `estados.py` (van por un plan resuelto por letra).
"""

from __future__ import annotations

from coop_contracts.intenciones import (
    IntCrearCredito,
    Intencion,
    IntRegRetiro,
)

from coop_bot.dialogo.entidades import SocioResuelto

PROMPT_CONFIRMACION = "¿Confirmas esta operación? Responde sí o no."

_INTERES_DEFAULT = 0.01


def formatear_monto(monto: int) -> str:
    """320000 -> '$320.000'. El monto siempre es un entero, nunca float."""
    return f"${monto:,.0f}".replace(",", ".")


def construir_resumen(
    intencion: Intencion,
    socios: dict[str, SocioResuelto],
    letras: dict[str, int],
    proxima_letra: int | None = None,
) -> str:
    if isinstance(intencion, IntRegRetiro):
        return _resumen_retiro(intencion, socios)
    if isinstance(intencion, IntCrearCredito):
        return _resumen_crear_credito(intencion, socios, proxima_letra)
    raise ValueError(f"construir_resumen no soporta la intención {intencion.intencion!r}")


def _resumen_crear_credito(
    intencion: IntCrearCredito, socios: dict[str, SocioResuelto], proxima_letra: int | None = None
) -> str:
    nombres = [socios[n].nombre_completo for n in intencion.socios]
    interes = intencion.interes if intencion.interes is not None else _INTERES_DEFAULT
    cuota_aprox = intencion.capital // intencion.n_cuotas
    lineas = ["Nuevo crédito:"]
    if proxima_letra is not None:
        lineas.append(f"- Letra: {proxima_letra}")
    lineas += [
        f"- Titular(es): {', '.join(nombres)}",
        f"- Capital: {formatear_monto(intencion.capital)}",
        f"- Cuotas: {intencion.n_cuotas} mensuales",
        f"- Interés: {interes * 100:.2f}% mensual",
        f"- Cuota aprox. a capital: {formatear_monto(cuota_aprox)}",
        "",
        PROMPT_CONFIRMACION,
    ]
    return "\n".join(lineas)


def _resumen_retiro(intencion: IntRegRetiro, socios: dict[str, SocioResuelto]) -> str:
    s = socios[intencion.socio]
    return (
        f"Retiro de {s.nombre_completo}: {formatear_monto(intencion.monto)} "
        f"(saldo actual: {formatear_monto(s.saldo)})\n\n{PROMPT_CONFIRMACION}"
    )

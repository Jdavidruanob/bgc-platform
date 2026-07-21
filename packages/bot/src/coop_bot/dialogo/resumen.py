"""Construcción del texto de confirmación mostrado al operador. Funciones puras, sin I/O."""

from __future__ import annotations

from coop_contracts.intenciones import (
    Intencion,
    IntRegAporte,
    IntRegCombinado,
    IntRegPago,
    IntRegRetiro,
    PagoItem,
)

from coop_bot.dialogo.entidades import SocioResuelto

PROMPT_CONFIRMACION = "¿Confirmas esta operación? Responde sí o no."


def formatear_monto(monto: int) -> str:
    """320000 -> '$320.000'. El monto siempre es un entero, nunca float."""
    return f"${monto:,.0f}".replace(",", ".")


def construir_resumen(
    intencion: Intencion,
    socios: dict[str, SocioResuelto],
    letras: dict[str, int],
) -> str:
    if isinstance(intencion, IntRegAporte):
        return _resumen_aporte(intencion, socios)
    if isinstance(intencion, IntRegRetiro):
        return _resumen_retiro(intencion, socios)
    if isinstance(intencion, IntRegPago):
        return _resumen_pago(intencion, socios, letras)
    if isinstance(intencion, IntRegCombinado):
        return _resumen_combinado(intencion, socios, letras)
    raise ValueError(f"construir_resumen no soporta la intención {intencion.intencion!r}")


def _resumen_aporte(intencion: IntRegAporte, socios: dict[str, SocioResuelto]) -> str:
    recibi_de = socios[intencion.recibi_de]
    lineas = [f"Recibí de: {recibi_de.nombre_completo}", "Aportes:"]
    for item in intencion.aportes:
        s = socios[item.nombre]
        lineas.append(
            f"- {s.nombre_completo}: {formatear_monto(item.monto)} (saldo actual: {formatear_monto(s.saldo)})"
        )
    lineas.append("")
    lineas.append(PROMPT_CONFIRMACION)
    return "\n".join(lineas)


def _resumen_retiro(intencion: IntRegRetiro, socios: dict[str, SocioResuelto]) -> str:
    s = socios[intencion.socio]
    return (
        f"Retiro de {s.nombre_completo}: {formatear_monto(intencion.monto)} "
        f"(saldo actual: {formatear_monto(s.saldo)})\n\n{PROMPT_CONFIRMACION}"
    )


def _resumen_pago(intencion: IntRegPago, socios: dict[str, SocioResuelto], letras: dict[str, int]) -> str:
    recibi_de = socios[intencion.recibi_de]
    lineas = [f"Recibí de: {recibi_de.nombre_completo}", "Pagos:"]
    for item in intencion.pagos:
        lineas.append(_linea_pago(item, socios, letras))
    lineas.append("")
    lineas.append(PROMPT_CONFIRMACION)
    return "\n".join(lineas)


def _resumen_combinado(
    intencion: IntRegCombinado, socios: dict[str, SocioResuelto], letras: dict[str, int]
) -> str:
    recibi_de = socios[intencion.recibi_de]
    lineas = [f"Recibí de: {recibi_de.nombre_completo}"]
    if intencion.aportes:
        lineas.append("Aportes:")
        for item in intencion.aportes:
            s = socios[item.nombre]
            lineas.append(
                f"- {s.nombre_completo}: {formatear_monto(item.monto)} "
                f"(saldo actual: {formatear_monto(s.saldo)})"
            )
    if intencion.pagos:
        lineas.append("Pagos:")
        for pago_item in intencion.pagos:
            lineas.append(_linea_pago(pago_item, socios, letras))
    lineas.append("")
    lineas.append(PROMPT_CONFIRMACION)
    return "\n".join(lineas)


def _linea_pago(item: PagoItem, socios: dict[str, SocioResuelto], letras: dict[str, int]) -> str:
    s = socios[item.nombre]
    letra_id = letras[item.nombre]
    if item.n_cuotas > 0:
        modo = f"{item.n_cuotas} cuota(s)"
    else:
        modo = f"abono a capital de {formatear_monto(item.abono_capital)}"
    return f"- {s.nombre_completo} (letra {letra_id}): {modo}"

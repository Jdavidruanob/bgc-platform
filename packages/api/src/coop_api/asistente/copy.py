"""Todos los textos en español del asistente de WhatsApp de socios, en un
solo lugar para poder ajustar el tono sin tocar la lógica de `flujo.py`.

Los ids de los botones del menú principal (`menu:*`) son el vocabulario que
entiende `flujo.py` — si cambian aquí, cambian ahí.
"""

from __future__ import annotations

from typing import Any

# (id, título) — título ≤ 20 caracteres, límite de Meta para botones.
MENU_PRINCIPAL: list[tuple[str, str]] = [
    ("menu:aportes", "Mi saldo de aportes"),
    ("menu:creditos", "Mis créditos"),
    ("menu:pagos", "Mis próximos pagos"),
]

BOTONES_LIQUIDACION_SI_NO: list[tuple[str, str]] = [
    ("liq:si", "Sí, por favor"),
    ("liq:no", "No, gracias"),
]


def primer_nombre(nombres: Any) -> str:
    partes = str(nombres or "").strip().split()
    return partes[0].capitalize() if partes else ""


def nombre_completo(socio: dict[str, Any]) -> str:
    return f"{socio.get('nombres', '')} {socio.get('apellidos', '')}".strip()


def saludo(socio: dict[str, Any]) -> str:
    return (
        f"Hola, {primer_nombre(socio.get('nombres'))} 👋\n\n"
        "Soy el asistente de BGC, con mucho gusto te ayudo.\n\n"
        "¿Qué deseas consultar?"
    )


def numero_no_reconocido() -> str:
    return (
        "Hola 👋 Soy el asistente de BGC.\n\n"
        "No encuentro tu número entre nuestros socios registrados, así que no "
        "puedo darte información por aquí. Si eres socio, comunícate con el "
        "tesorero para que actualice tu número. 🙏"
    )


def no_puedo_escuchar_audio() -> str:
    return "Por ahora no puedo escuchar notas de voz 🙈 Usa los botones y con gusto te ayudo."


def opcion_no_reconocida(socio: dict[str, Any]) -> str:
    return (
        f"Perdón, {primer_nombre(socio.get('nombres'))}, no reconocí esa opción 🙈\n\n"
        "Te dejo el menú de nuevo:"
    )


def saldo_de_aportes(socio: dict[str, Any], saldo_formateado: str) -> str:
    return f"El saldo de aportes de {nombre_completo(socio)} es: ${saldo_formateado} 💰"


def sin_creditos_activos(socio: dict[str, Any]) -> str:
    return f"En este momento no tienes créditos activos, {primer_nombre(socio.get('nombres'))} 😊"


def mis_creditos(letras: list[int]) -> str:
    if len(letras) == 1:
        cabecera = f"Tienes 1 crédito activo: letra #{letras[0]}."
    else:
        listado = ", ".join(f"#{n}" for n in letras)
        cabecera = f"Tienes {len(letras)} créditos activos: letra {listado}."
    plural = "de tus créditos" if len(letras) > 1 else "de tu crédito"
    return f"{cabecera}\n\n¿Deseas que te envíe la liquidación a día de hoy {plural}?"


def elegir_credito() -> str:
    return "¿De cuál crédito te envío la liquidación?"


def liquidacion_no_gracias(socio: dict[str, Any]) -> str:
    return f"Listo, {primer_nombre(socio.get('nombres'))}, cuando quieras aquí estoy 😊"


def preparando_liquidacion() -> str:
    return "Dame un momento, estoy preparando tu liquidación 📄"


def liquidacion_caption(letra_id: int, fecha_hoy: str) -> str:
    return f"Liquidación al día de hoy ({fecha_hoy}) de tu crédito con letra #{letra_id} ✅"


def liquidacion_no_disponible() -> str:
    return "Ahora mismo no puedo generar ese documento 😕 Inténtalo de nuevo en unos minutos."


def sin_pagos_pendientes(socio: dict[str, Any]) -> str:
    return f"No tienes pagos pendientes en este momento, {primer_nombre(socio.get('nombres'))} 🎉"


def encabezado_proximos_pagos(socio: dict[str, Any]) -> str:
    return f"Estos son tus próximos pagos, {primer_nombre(socio.get('nombres'))}:"


def linea_cuota_vencida(letra_id: int, nro_cuota: int, cuota_total: int, fecha: str, mora: int) -> str:
    from coop_core.utils.formato import format_miles_colombian_int

    monto = format_miles_colombian_int(cuota_total)
    if mora > 0:
        return (
            f"• Letra #{letra_id}, cuota #{nro_cuota} — paga ${monto} "
            f"(venció el {fecha}, mora ${format_miles_colombian_int(mora)})"
        )
    return f"• Letra #{letra_id}, cuota #{nro_cuota} — paga ${monto} (venció el {fecha})"


def linea_proximo_pago(letra_id: int, nro_cuota: int, cuota_total: int, fecha: str) -> str:
    from coop_core.utils.formato import format_miles_colombian_int

    monto = format_miles_colombian_int(cuota_total)
    return f"• Letra #{letra_id}, cuota #{nro_cuota} — paga ${monto} para el {fecha}"

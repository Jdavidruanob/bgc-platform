"""Textos de ayuda que el bot da cuando el operador pregunta qué puede hacer.

Son respuestas fijas (no llaman a la API ni al LLM). El LLM solo clasifica la
pregunta en un tema; aquí vive el texto que se le muestra a Álvaro/Mary.
"""

from __future__ import annotations

_AYUDA_GENERAL = (
    "Soy tu asistente de la cooperativa BGC. Puedo ayudarte con:\n\n"
    "• *Aportes*: dime quién aporta y cuánto.\n"
    "   Ej: «Pedro aporta 80 mil»\n"
    "• *Pagos de cuotas*: quién paga, de qué crédito y cuántas cuotas.\n"
    "   Ej: «María paga 2 cuotas de la letra 450»\n"
    "• *Retiros*: quién retira y cuánto.\n"
    "   Ej: «Juan retira 200 mil»\n"
    "• *Crear créditos*: para quién, el monto y en cuántas cuotas.\n"
    "   Ej: «Un crédito para Pedro de un millón a 12 cuotas»\n"
    "• *Consultas*: el saldo de un socio, las cuotas de un crédito, "
    "o cuánto hay en caja.\n\n"
    "Puedes escribirme o mandarme una nota de voz. "
    "Si te falta algún dato, yo te lo pregunto."
)

_AYUDA_CREDITO = (
    "Para crear un crédito solo dime tres cosas:\n"
    "1. Para quién es (uno o varios socios)\n"
    "2. El monto del capital\n"
    "3. En cuántas cuotas\n\n"
    "Ejemplo: «Crear un crédito para Pedro Gómez de dos millones a 12 cuotas».\n\n"
    "Si no me dices el interés, uso el 1% mensual. Si quieres otro, agrégalo: "
    "«al 1.5 por ciento». Cuando confirmes, te mando la liquidación en PDF."
)

_AYUDA_RECIBO = (
    "Para hacer un recibo solo cuéntame qué operación es. Puede ser un aporte, "
    "un pago de cuota, un retiro, o varios juntos en el mismo recibo. Ejemplos:\n\n"
    "• «Pedro aporta 80 mil»\n"
    "• «María paga 2 cuotas de la letra 450»\n"
    "• «Pedro aporta 50 mil y paga una cuota de la 320»\n\n"
    "El primer socio que menciones es de quien recibo el dinero. "
    "Yo armo el recibo y te lo mando en PDF."
)

_AYUDA_APORTE = (
    "Para registrar un aporte dime quién aporta y cuánto.\n"
    "Ejemplo: «Pedro Gómez aporta 80 mil».\n"
    "Puedes registrar varios en un mismo recibo: "
    "«Pedro aporta 80 mil y María 50 mil»."
)

_AYUDA_PAGO = (
    "Para registrar un pago de cuota dime quién paga, de qué crédito y cuántas "
    "cuotas.\n"
    "Ejemplo: «María López paga 2 cuotas de la letra 450».\n"
    "También puede ser un abono a capital: «Pedro abona 100 mil a su crédito»."
)

_AYUDA_RETIRO = "Para registrar un retiro dime quién retira y cuánto.\nEjemplo: «Juan Pérez retira 200 mil»."

_AYUDA_CONSULTA = (
    "Puedo consultarte:\n"
    "• El saldo de un socio: «¿Cuánto tiene Pedro Gómez?»\n"
    "• Las cuotas pendientes de un crédito: «Cuotas de la letra 450»\n"
    "• Cuánto hay en caja: «¿Cómo está la caja?»"
)

_POR_TEMA: dict[str, str] = {
    "general": _AYUDA_GENERAL,
    "credito": _AYUDA_CREDITO,
    "crédito": _AYUDA_CREDITO,
    "recibo": _AYUDA_RECIBO,
    "aporte": _AYUDA_APORTE,
    "pago": _AYUDA_PAGO,
    "retiro": _AYUDA_RETIRO,
    "consulta": _AYUDA_CONSULTA,
}


def texto_ayuda(tema: str | None) -> str:
    if tema is None:
        return _AYUDA_GENERAL
    return _POR_TEMA.get(tema.strip().lower(), _AYUDA_GENERAL)

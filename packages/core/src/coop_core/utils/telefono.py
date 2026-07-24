"""Derivación del número de WhatsApp de un socio.

La mayoría de socios solo tienen `celular` cargado (el dato histórico del
BGC-software); `whatsapp_e164` es el campo explícito para cuando se confirme el
número por WhatsApp. Mientras tanto, se deriva de `celular` si tiene la forma de
un celular colombiano (10 dígitos, empieza en 3).
"""

from __future__ import annotations


def derivar_whatsapp_e164(whatsapp_e164: str | None, celular: str | None) -> str | None:
    if whatsapp_e164:
        return whatsapp_e164
    if not celular:
        return None
    digitos = "".join(c for c in celular if c.isdigit())
    if len(digitos) == 10 and digitos.startswith("3"):
        return f"+57{digitos}"
    return None

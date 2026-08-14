"""Configuración del asistente de WhatsApp para socios, leída de variables de
entorno del servicio API (distintas de las del bot, aunque el token y el
phone_number_id normalmente son los mismos)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigAsistente:
    token: str | None
    phone_number_id: str | None
    verify_token: str | None
    app_secret: str | None
    graph_version: str
    numeros_autorizados: frozenset[str] | None
    """None = nadie autorizado (default seguro). frozenset vacío no existe:
    si la variable está vacía se trata como no configurada. `{"*"}` = todos."""

    @property
    def credenciales_completas(self) -> bool:
        return bool(self.token and self.phone_number_id and self.verify_token and self.app_secret)

    def numero_autorizado(self, numero_e164: str) -> bool:
        if not self.numeros_autorizados:
            return False
        if "*" in self.numeros_autorizados:
            return True
        return numero_e164 in self.numeros_autorizados


def _leer_numeros_autorizados() -> frozenset[str] | None:
    crudo = os.environ.get("WHATSAPP_ASISTENTE_NUMEROS", "").strip()
    if not crudo:
        return None
    return frozenset(n.strip() for n in crudo.split(",") if n.strip())


def desde_entorno() -> ConfigAsistente:
    return ConfigAsistente(
        token=os.environ.get("WHATSAPP_CLOUD_API_TOKEN") or None,
        phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or None,
        verify_token=os.environ.get("WHATSAPP_VERIFY_TOKEN") or None,
        app_secret=os.environ.get("WHATSAPP_APP_SECRET") or None,
        graph_version=os.environ.get("WHATSAPP_GRAPH_VERSION", "v20.0"),
        numeros_autorizados=_leer_numeros_autorizados(),
    )

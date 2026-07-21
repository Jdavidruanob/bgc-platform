from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Falta una variable de entorno requerida o tiene un valor inválido."""


def _req(nombre: str) -> str:
    valor = os.environ.get(nombre)
    if not valor:
        raise ConfigError(f"Falta la variable de entorno {nombre}")
    return valor


@dataclass(frozen=True)
class Config:
    coop_api_base_url: str
    coop_api_token: str
    telegram_bot_token: str
    telegram_operador_chat_id: int
    openai_api_key: str
    log_level: str = "INFO"
    whatsapp_cloud_api_token: str | None = None
    whatsapp_phone_number_id: str | None = None

    @classmethod
    def desde_entorno(cls) -> Config:
        chat_id_raw = _req("TELEGRAM_OPERADOR_CHAT_ID")
        try:
            chat_id = int(chat_id_raw)
        except ValueError as exc:
            raise ConfigError(
                f"TELEGRAM_OPERADOR_CHAT_ID debe ser un entero, se recibió: {chat_id_raw!r}"
            ) from exc

        return cls(
            coop_api_base_url=_req("COOP_API_BASE_URL"),
            coop_api_token=_req("COOP_API_TOKEN"),
            telegram_bot_token=_req("TELEGRAM_BOT_TOKEN"),
            telegram_operador_chat_id=chat_id,
            openai_api_key=_req("OPENAI_API_KEY"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            whatsapp_cloud_api_token=os.environ.get("WHATSAPP_CLOUD_API_TOKEN") or None,
            whatsapp_phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or None,
        )

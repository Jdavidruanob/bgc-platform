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
    # Chat IDs autorizados a hablar con el bot (Álvaro, Mari, y quien esté probando).
    telegram_operador_chat_ids: tuple[int, ...]
    openai_api_key: str
    log_level: str = "INFO"
    whatsapp_cloud_api_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    # Plantilla de utilidad aprobada por Meta. Sin ella solo se puede escribir
    # a socios que hayan escrito en las últimas 24h (ver ADR-010).
    whatsapp_plantilla: str | None = None
    whatsapp_plantilla_idioma: str = "es"

    @property
    def telegram_operador_chat_id(self) -> int:
        """Primer operador. Se mantiene por compatibilidad; el bot autoriza a
        cualquiera en `telegram_operador_chat_ids`."""
        return self.telegram_operador_chat_ids[0]

    def es_operador_autorizado(self, chat_id: int) -> bool:
        return chat_id in self.telegram_operador_chat_ids

    @classmethod
    def desde_entorno(cls) -> Config:
        chat_ids = cls._leer_operadores()
        return cls(
            coop_api_base_url=_req("COOP_API_BASE_URL"),
            coop_api_token=_req("COOP_API_TOKEN"),
            telegram_bot_token=_req("TELEGRAM_BOT_TOKEN"),
            telegram_operador_chat_ids=chat_ids,
            openai_api_key=_req("OPENAI_API_KEY"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            whatsapp_cloud_api_token=os.environ.get("WHATSAPP_CLOUD_API_TOKEN") or None,
            whatsapp_phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or None,
            whatsapp_plantilla=os.environ.get("WHATSAPP_PLANTILLA") or None,
            whatsapp_plantilla_idioma=os.environ.get("WHATSAPP_PLANTILLA_IDIOMA") or "es",
        )

    @staticmethod
    def _leer_operadores() -> tuple[int, ...]:
        """Acepta `TELEGRAM_OPERADOR_CHAT_IDS` (varios, separados por coma) o el
        singular `TELEGRAM_OPERADOR_CHAT_ID` por compatibilidad. Al menos uno es
        obligatorio."""
        raw = os.environ.get("TELEGRAM_OPERADOR_CHAT_IDS") or os.environ.get("TELEGRAM_OPERADOR_CHAT_ID")
        if not raw:
            raise ConfigError(
                "Falta la variable de entorno TELEGRAM_OPERADOR_CHAT_IDS (o TELEGRAM_OPERADOR_CHAT_ID)"
            )
        ids: list[int] = []
        for parte in raw.split(","):
            parte = parte.strip()
            if not parte:
                continue
            try:
                ids.append(int(parte))
            except ValueError as exc:
                raise ConfigError(
                    f"TELEGRAM_OPERADOR_CHAT_IDS debe ser enteros separados por coma, "
                    f"valor inválido: {parte!r}"
                ) from exc
        if not ids:
            raise ConfigError("TELEGRAM_OPERADOR_CHAT_IDS no contiene ningún ID válido")
        return tuple(ids)

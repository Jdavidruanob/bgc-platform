"""Punto de entrada del bot.

Uso:
    uv run --package coop-bot python -m coop_bot.main --modo=polling
    uv run --package coop-bot python -m coop_bot.main --modo=webhook \
        --webhook-url=https://coop-bot.fly.dev/webhook --puerto=8080
"""

from __future__ import annotations

import argparse
import logging

from telegram.ext import ApplicationBuilder

from coop_bot.adaptadores.telegram import registrar_handlers, registrar_jobs
from coop_bot.api.cliente import ApiClient
from coop_bot.config import Config
from coop_bot.nlu.llm_client import LlmClient
from coop_bot.nlu.whisper_client import WhisperClient
from coop_bot.notificaciones.notificadores import construir_notificador


def _parsear_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bot de mensajería de la cooperativa")
    parser.add_argument("--modo", choices=["polling", "webhook"], default="polling")
    parser.add_argument("--webhook-url", default=None, help="URL pública para el modo webhook")
    parser.add_argument("--puerto", type=int, default=8080, help="Puerto local para el webhook")
    return parser.parse_args()


def main() -> None:
    args = _parsear_args()
    config = Config.desde_entorno()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    application = ApplicationBuilder().token(config.telegram_bot_token).build()
    application.bot_data["config"] = config
    application.bot_data["api_client"] = ApiClient(
        base_url=config.coop_api_base_url, token=config.coop_api_token
    )
    application.bot_data["whisper_client"] = WhisperClient(api_key=config.openai_api_key)
    application.bot_data["llm_client"] = LlmClient(api_key=config.openai_api_key)
    application.bot_data["notificador"] = construir_notificador(config)

    registrar_handlers(application)
    registrar_jobs(application)

    if args.modo == "polling":
        application.run_polling()
    else:
        if not args.webhook_url:
            raise SystemExit("--webhook-url es requerido en modo webhook")
        application.run_webhook(
            listen="0.0.0.0",
            port=args.puerto,
            webhook_url=args.webhook_url,
        )


if __name__ == "__main__":
    main()

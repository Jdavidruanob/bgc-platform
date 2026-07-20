from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ResultadoEnvio(BaseModel):
    exitoso: bool
    canal: str  # "cloud_api" | "wa_me_link" | "mock"
    wa_me_url: str | None = None
    error: str | None = None


@runtime_checkable
class Notificador(Protocol):
    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio: ...


class MockNotificador:
    """Implementación de pruebas: registra los envíos en memoria sin hacer llamadas externas."""

    def __init__(self) -> None:
        self.enviados: list[dict[str, str]] = []

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        self.enviados.append({"numero_e164": numero_e164, "texto": texto})
        return ResultadoEnvio(exitoso=True, canal="mock")

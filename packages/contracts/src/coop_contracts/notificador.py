from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ResultadoEnvio(BaseModel):
    exitoso: bool
    canal: str  # "cloud_api" | "wa_me_link" | "mock"
    wa_me_url: str | None = None
    error: str | None = None


class ParamsPlantilla(BaseModel):
    """Variables de la plantilla de utilidad aprobada por Meta.

    Meta rechaza valores de variable con saltos de línea, tabulaciones o más
    de 4 espacios seguidos, así que ambos campos deben ir en una sola línea
    (`limpiar()` lo garantiza).
    """

    nombre: str  # {{1}} — nombre de pila del socio
    detalle: str  # {{2}} — resumen de la operación en una línea

    def limpiar(self) -> ParamsPlantilla:
        return ParamsPlantilla(nombre=_una_linea(self.nombre), detalle=_una_linea(self.detalle))


def _una_linea(valor: str) -> str:
    return " ".join(valor.split())


@runtime_checkable
class Notificador(Protocol):
    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio: ...

    def enviar_documento(
        self,
        numero_e164: str,
        texto: str,
        contenido: bytes,
        nombre_archivo: str,
        plantilla: ParamsPlantilla | None = None,
    ) -> ResultadoEnvio: ...


class MockNotificador:
    """Implementación de pruebas: registra los envíos en memoria sin hacer llamadas externas."""

    def __init__(self) -> None:
        self.enviados: list[dict[str, str]] = []
        self.documentos_enviados: list[dict[str, str]] = []

    def enviar(self, numero_e164: str, texto: str) -> ResultadoEnvio:
        self.enviados.append({"numero_e164": numero_e164, "texto": texto})
        return ResultadoEnvio(exitoso=True, canal="mock")

    def enviar_documento(
        self,
        numero_e164: str,
        texto: str,
        contenido: bytes,
        nombre_archivo: str,
        plantilla: ParamsPlantilla | None = None,
    ) -> ResultadoEnvio:
        self.documentos_enviados.append(
            {
                "numero_e164": numero_e164,
                "texto": texto,
                "nombre_archivo": nombre_archivo,
                "plantilla": plantilla.detalle if plantilla else "",
            }
        )
        return ResultadoEnvio(exitoso=True, canal="mock")

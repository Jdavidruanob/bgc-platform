from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

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
    documento: str  # {{2}} — sustantivo genérico del documento adjunto: "recibo" o "liquidación"

    def limpiar(self) -> ParamsPlantilla:
        return ParamsPlantilla(nombre=_una_linea(self.nombre), documento=_una_linea(self.documento))


class ParamsRecordatorio(BaseModel):
    """Variables de la plantilla de recordatorio de mora próxima (sin
    documento adjunto, ver ADR-010): la cuota vence hoy y avisa cuántos días
    de gracia le quedan antes de que se le cobre mora."""

    nombre: str  # {{1}} — nombre de pila del socio
    numero_cuota: str  # {{2}}
    numero_letra: str  # {{3}}
    fecha_pago_cuota: str  # {{4}} — fecha de vencimiento (hoy)
    fecha_mora: str  # {{5}} — fecha de vencimiento + días de gracia
    monto_mora: str  # {{6}} — mora que se cobraría si no paga antes de fecha_mora

    def limpiar(self) -> ParamsRecordatorio:
        return ParamsRecordatorio(
            nombre=_una_linea(self.nombre),
            numero_cuota=_una_linea(self.numero_cuota),
            numero_letra=_una_linea(self.numero_letra),
            fecha_pago_cuota=_una_linea(self.fecha_pago_cuota),
            fecha_mora=_una_linea(self.fecha_mora),
            monto_mora=_una_linea(self.monto_mora),
        )


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

    def enviar_recordatorio(
        self, numero_e164: str, texto: str, plantilla: ParamsRecordatorio | None = None
    ) -> ResultadoEnvio: ...


class MockNotificador:
    """Implementación de pruebas: registra los envíos en memoria sin hacer llamadas externas."""

    def __init__(self) -> None:
        self.enviados: list[dict[str, str]] = []
        self.documentos_enviados: list[dict[str, str]] = []
        self.recordatorios_enviados: list[dict[str, Any]] = []

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
                "plantilla": plantilla.documento if plantilla else "",
            }
        )
        return ResultadoEnvio(exitoso=True, canal="mock")

    def enviar_recordatorio(
        self, numero_e164: str, texto: str, plantilla: ParamsRecordatorio | None = None
    ) -> ResultadoEnvio:
        self.recordatorios_enviados.append(
            {
                "numero_e164": numero_e164,
                "texto": texto,
                "plantilla": plantilla.model_dump() if plantilla else {},
            }
        )
        return ResultadoEnvio(exitoso=True, canal="mock")

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class AporteItem(BaseModel):
    nombre: str = Field(..., description="Nombre del socio tal como fue mencionado")
    monto: Annotated[int, Field(gt=0)] = Field(..., description="Monto en pesos enteros")


class PagoItem(BaseModel):
    nombre: str
    letra_id_hint: str | None = Field(
        None,
        description="Número de letra si el usuario lo mencionó explícitamente. Null si no.",
    )
    n_cuotas: Annotated[int, Field(ge=0)] = 0
    abono_capital: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validar_modo_pago(self) -> PagoItem:
        if self.n_cuotas > 0 and self.abono_capital > 0:
            raise ValueError("n_cuotas y abono_capital son excluyentes")
        if self.n_cuotas == 0 and self.abono_capital == 0:
            raise ValueError("Debe especificarse n_cuotas o abono_capital")
        return self


class IntRegAporte(BaseModel):
    intencion: Literal["registrar_aporte"]
    recibi_de: str = Field(..., description="Nombre del socio que entrega el dinero")
    aportes: list[AporteItem] = Field(..., min_length=1)


class IntRegRetiro(BaseModel):
    intencion: Literal["registrar_retiro"]
    socio: str = Field(..., description="Nombre del socio que retira")
    monto: Annotated[int, Field(gt=0)]


class IntRegPago(BaseModel):
    intencion: Literal["registrar_pago"]
    recibi_de: str
    pagos: list[PagoItem] = Field(..., min_length=1)


class IntRegCombinado(BaseModel):
    intencion: Literal["registrar_combinado"]
    recibi_de: str
    aportes: list[AporteItem]
    pagos: list[PagoItem]

    @model_validator(mode="after")
    def al_menos_una_operacion(self) -> IntRegCombinado:
        if not self.aportes and not self.pagos:
            raise ValueError("Debe haber al menos un aporte o un pago")
        return self


class IntCrearCredito(BaseModel):
    intencion: Literal["crear_credito"]
    socios: list[str] = Field(..., min_length=1, description="Nombres de los socios titulares")
    capital: Annotated[int, Field(gt=0)] = Field(..., description="Monto del crédito en pesos")
    n_cuotas: Annotated[int, Field(gt=0)] = Field(..., description="Número de cuotas mensuales")
    interes: float | None = Field(
        default=None, description="Tasa mensual en fracción (0.01 = 1%). Null si no se mencionó."
    )


class IntConsultarSocio(BaseModel):
    intencion: Literal["consultar_socio"]
    socio: str


class IntConsultarCuotas(BaseModel):
    intencion: Literal["consultar_cuotas"]
    socio: str
    letra_id_hint: str | None = None


class IntConsultarCaja(BaseModel):
    intencion: Literal["consultar_caja"]


class IntAyuda(BaseModel):
    intencion: Literal["ayuda"]
    # Sobre qué pide ayuda: "credito", "recibo", "aporte", "pago", "retiro",
    # "consulta" o "general" (o null para ayuda general).
    tema: str | None = None


class IntDesconocida(BaseModel):
    intencion: Literal["desconocida"]
    texto_original: str


class IntIncompleta(BaseModel):
    intencion: Literal["incompleta"]
    intencion_detectada: str = Field(..., description="Intención detectada pero incompleta")
    campos_faltantes: list[str] = Field(..., description="Campos que faltan para completar")
    texto_original: str


class IntAmbigua(BaseModel):
    intencion: Literal["ambigua"]
    posibles_intenciones: list[str]
    texto_original: str


Intencion = (
    IntRegAporte
    | IntRegRetiro
    | IntRegPago
    | IntRegCombinado
    | IntCrearCredito
    | IntConsultarSocio
    | IntConsultarCuotas
    | IntConsultarCaja
    | IntAyuda
    | IntDesconocida
    | IntIncompleta
    | IntAmbigua
)

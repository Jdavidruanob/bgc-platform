from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class AporteItem(BaseModel):
    nombre: str = Field(..., description="Nombre del socio tal como fue mencionado")
    monto: Annotated[int, Field(gt=0)] = Field(..., description="Monto en pesos enteros")
    familia: bool = Field(
        default=False,
        description="Si es True, el monto se aporta a CADA miembro de la familia de `nombre`.",
    )


class PagoItem(BaseModel):
    # El pago se identifica por la LETRA (única). El nombre es opcional: sirve
    # para confirmar, o para resolver la letra cuando no se dio el número.
    nombre: str | None = None
    letra_id_hint: str | None = Field(
        None,
        description="Número de letra si el usuario lo mencionó explícitamente. Null si no.",
    )
    todas_las_letras: bool = Field(
        default=False,
        description="Si es True, se paga a TODAS las letras del socio `nombre`.",
    )
    n_cuotas: Annotated[int, Field(ge=0)] = 0
    abono_capital: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validar_modo_pago(self) -> PagoItem:
        if self.n_cuotas > 0 and self.abono_capital > 0:
            raise ValueError("n_cuotas y abono_capital son excluyentes")
        if self.n_cuotas == 0 and self.abono_capital == 0:
            raise ValueError("Debe especificarse n_cuotas o abono_capital")
        if self.todas_las_letras:
            if not self.nombre:
                raise ValueError("todas_las_letras requiere el nombre del socio")
            if self.letra_id_hint is not None:
                raise ValueError("todas_las_letras no se combina con una letra específica")
            if self.abono_capital > 0:
                raise ValueError("todas_las_letras solo aplica con n_cuotas, no abono a capital")
        elif not self.nombre and self.letra_id_hint is None:
            raise ValueError("Cada pago necesita la letra o el nombre del socio")
        return self


class IntRegAporte(BaseModel):
    intencion: Literal["registrar_aporte"]
    # Quien entrega el dinero. Opcional: si no se dice, es el primer socio.
    recibi_de: str | None = None
    aportes: list[AporteItem] = Field(..., min_length=1)


class IntRegRetiro(BaseModel):
    intencion: Literal["registrar_retiro"]
    socio: str = Field(..., description="Nombre del socio que retira")
    monto: Annotated[int, Field(gt=0)]


class IntRegPago(BaseModel):
    intencion: Literal["registrar_pago"]
    # Opcional: con letra basta. Si no se dice, es el titular de la primera letra.
    recibi_de: str | None = None
    pagos: list[PagoItem] = Field(..., min_length=1)


class IntRegCombinado(BaseModel):
    intencion: Literal["registrar_combinado"]
    recibi_de: str | None = None
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


class IntListarSocios(BaseModel):
    intencion: Literal["listar_socios"]


class IntConsultarCreditos(BaseModel):
    intencion: Literal["consultar_creditos"]
    socio: str


class IntConsultarFamilia(BaseModel):
    intencion: Literal["consultar_familia"]
    socio: str


class IntPedirExcel(BaseModel):
    """El operador pide el último documento en Excel en vez de/además de PDF.
    Sin parámetros: aplica al último documento generado en la sesión."""

    intencion: Literal["pedir_excel"]


class IntPagoSalario(BaseModel):
    intencion: Literal["pago_salario"]
    # Mes que se paga (en palabra). Null = el mes actual.
    mes: str | None = None
    # Monto si el operador lo dijo explícito. Null = usar el salario sugerido.
    monto: Annotated[int, Field(gt=0)] | None = None


class IntLiquidacionLetra(BaseModel):
    intencion: Literal["liquidacion_letra"]
    letras: list[int] = Field(..., min_length=1, description="Una o varias letras a liquidar")


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
    | IntListarSocios
    | IntConsultarCreditos
    | IntConsultarFamilia
    | IntLiquidacionLetra
    | IntPagoSalario
    | IntPedirExcel
    | IntAyuda
    | IntDesconocida
    | IntIncompleta
    | IntAmbigua
)

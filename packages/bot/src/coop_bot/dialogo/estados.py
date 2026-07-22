"""Máquina de estados del diálogo con el operador.

Agnóstica de Telegram a propósito: no importa `telegram`/`telegram.ext`, para
poder testearse sin construir objetos de PTB. El timeout de 5 minutos y la
cancelación se expresan como flags en `RespuestaDialogo`; quien realmente
programa/cancela el job es el adaptador de Telegram.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from coop_contracts.intenciones import (
    IntAmbigua,
    IntConsultarCaja,
    IntConsultarCuotas,
    IntConsultarSocio,
    IntCrearCredito,
    IntDesconocida,
    Intencion,
    IntIncompleta,
    IntRegAporte,
    IntRegCombinado,
    IntRegPago,
    IntRegRetiro,
    PagoItem,
)
from coop_contracts.respuestas import (
    AporteReqItem,
    AportesRequest,
    CombinadosRequest,
    CreditoResumen,
    PagoReqItem,
    PagosRequest,
    RetirosRequest,
    SocioSearchItem,
)

from coop_bot.api.cliente import ApiClient, ApiError
from coop_bot.dialogo.entidades import (
    SocioResuelto,
    formatear_lista_letras,
    formatear_lista_socios,
    parsear_seleccion,
    resolver_letra,
    resolver_socio,
)
from coop_bot.dialogo.resumen import PROMPT_CONFIRMACION, construir_resumen, formatear_monto
from coop_bot.pdf.generador import (
    generar_pdf_recibo,
    generar_pdf_tabla_cuotas,
    nombre_archivo_cuotas,
    nombre_archivo_recibo,
    recibo_desde_aportes,
    recibo_desde_combinado,
    recibo_desde_pagos,
    recibo_desde_retiro,
)

TIMEOUT_SEGUNDOS = 300  # 5 minutos

_AFIRMACIONES = {"si", "sí", "confirmo", "dale", "ok", "listo", "correcto", "s"}
_NEGACIONES = {"no", "cancelar", "cancela", "n"}


class EstadoDialogo(StrEnum):
    ESPERANDO_MENSAJE = "esperando_mensaje"
    PROCESANDO = "procesando"
    ESPERANDO_DESAMBIGUACION = "esperando_desambiguacion"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    EJECUTANDO = "ejecutando"
    RESPONDIENDO = "respondiendo"


@dataclass
class SeleccionPendiente:
    tipo: Literal["socio", "letra"]
    etiqueta: str
    candidatos_socio: list[SocioSearchItem] = field(default_factory=list)
    candidatos_letra: list[CreditoResumen] = field(default_factory=list)


@dataclass
class SesionDialogo:
    chat_id: int
    estado: EstadoDialogo = EstadoDialogo.ESPERANDO_MENSAJE
    intencion: Intencion | None = None
    socios: dict[str, SocioResuelto] = field(default_factory=dict)
    letras: dict[str, int] = field(default_factory=dict)
    pendientes: deque[SeleccionPendiente] = field(default_factory=deque)
    idempotency_key: str | None = None
    resumen_texto: str | None = None
    texto_acumulado: str | None = None
    actualizado_en: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RespuestaDialogo:
    texto: str
    requiere_timeout: bool = False
    cancelar_timeout: bool = False
    documento_pdf: bytes | None = None
    nombre_documento: str | None = None


class MaquinaEstados:
    def __init__(self, sesion: SesionDialogo, cliente: ApiClient) -> None:
        self.sesion = sesion
        self.cliente = cliente

    # ── Entradas públicas ────────────────────────────────────────────────────

    async def procesar_intencion(self, intencion: Intencion) -> RespuestaDialogo:
        if isinstance(intencion, IntDesconocida):
            self.sesion.texto_acumulado = None
            return self._quedarse_en_espera("No entendí tu mensaje. ¿Puedes repetirlo de otra forma?")
        if isinstance(intencion, IntIncompleta):
            self.sesion.texto_acumulado = intencion.texto_original
            pregunta = _pregunta_por_faltantes(intencion.intencion_detectada, intencion.campos_faltantes)
            return self._quedarse_en_espera(pregunta)
        if isinstance(intencion, IntAmbigua):
            self.sesion.texto_acumulado = None
            opciones = ", ".join(intencion.posibles_intenciones)
            return self._quedarse_en_espera(
                f"No me quedó claro qué operación quieres hacer. ¿Te refieres a: {opciones}?"
            )
        if isinstance(intencion, IntCrearCredito):
            self.sesion.texto_acumulado = None
            return self._quedarse_en_espera("Esa función todavía no está disponible desde el bot.")
        if not isinstance(
            intencion,
            IntRegAporte
            | IntRegRetiro
            | IntRegPago
            | IntRegCombinado
            | IntConsultarSocio
            | IntConsultarCuotas
            | IntConsultarCaja,
        ):
            self.sesion.texto_acumulado = None
            return self._quedarse_en_espera("No pude procesar esa solicitud.")

        self.sesion.texto_acumulado = None
        self.sesion.intencion = intencion
        self.sesion.estado = EstadoDialogo.PROCESANDO
        return await self._resolver_entidades_y_continuar()

    async def recibir_respuesta_desambiguacion(self, texto: str) -> RespuestaDialogo:
        if _es_negacion(texto):
            return self._cancelar("Operación cancelada.")
        if not self.sesion.pendientes:
            return self._cancelar("Ocurrió un problema con la desambiguación. Intenta de nuevo.")

        pendiente = self.sesion.pendientes[0]
        if pendiente.tipo == "socio":
            return await self._recibir_seleccion_socio(pendiente, texto)
        return await self._recibir_seleccion_letra(pendiente, texto)

    async def recibir_confirmacion(self, texto: str) -> RespuestaDialogo:
        if _es_negacion(texto):
            return self._cancelar("Operación cancelada. No se guardó nada.")
        if not _es_afirmacion(texto):
            return RespuestaDialogo(
                texto=f"No entendí tu respuesta. {PROMPT_CONFIRMACION}",
                requiere_timeout=True,
            )

        self.sesion.estado = EstadoDialogo.EJECUTANDO
        if self.sesion.idempotency_key is None:
            self.sesion.idempotency_key = str(uuid4())

        try:
            pdf_bytes, nombre_pdf = await self._ejecutar_operacion()
        except ApiError as exc:
            self._reset_operacion()
            self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
            return RespuestaDialogo(texto=exc.mensaje, cancelar_timeout=True)

        self.sesion.estado = EstadoDialogo.RESPONDIENDO
        self._reset_operacion()
        self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
        return RespuestaDialogo(
            texto="Listo, aquí está tu comprobante.",
            documento_pdf=pdf_bytes,
            nombre_documento=nombre_pdf,
            cancelar_timeout=True,
        )

    def cancelar_por_timeout(self) -> RespuestaDialogo:
        return self._cancelar("Operación cancelada por inactividad (pasaron más de 5 minutos).")

    def cancelar_explicito(self) -> RespuestaDialogo:
        return self._cancelar("Operación cancelada.")

    # ── Resolución de entidades ──────────────────────────────────────────────

    async def _resolver_entidades_y_continuar(self) -> RespuestaDialogo:
        intencion = self.sesion.intencion
        assert intencion is not None

        for nombre in _nombres_socios(intencion):
            if nombre in self.sesion.socios:
                continue
            resolucion = await resolver_socio(self.cliente, nombre)
            if resolucion.estado == "no_encontrado":
                return self._cancelar(
                    f"No encontré ningún socio llamado '{nombre}'. Verifica el nombre e intenta de nuevo."
                )
            if resolucion.estado == "ambiguo":
                self.sesion.pendientes.append(
                    SeleccionPendiente(tipo="socio", etiqueta=nombre, candidatos_socio=resolucion.candidatos)
                )
                self.sesion.estado = EstadoDialogo.ESPERANDO_DESAMBIGUACION
                return RespuestaDialogo(
                    texto=(
                        f"Hay varios socios que coinciden con '{nombre}':\n"
                        f"{formatear_lista_socios(resolucion.candidatos)}"
                    ),
                    requiere_timeout=True,
                )
            assert resolucion.resuelto is not None
            self.sesion.socios[nombre] = resolucion.resuelto

        for nombre, letra_hint in _nombres_letras(intencion):
            if nombre in self.sesion.letras:
                continue
            socio_id = self.sesion.socios[nombre].id
            resolucion_letra = await resolver_letra(self.cliente, socio_id, letra_hint)
            if resolucion_letra.estado == "no_encontrado":
                return self._cancelar(
                    f"{self.sesion.socios[nombre].nombre_completo} no tiene créditos activos."
                )
            if resolucion_letra.estado == "ambiguo":
                self.sesion.pendientes.append(
                    SeleccionPendiente(
                        tipo="letra",
                        etiqueta=nombre,
                        candidatos_letra=resolucion_letra.candidatos,
                    )
                )
                self.sesion.estado = EstadoDialogo.ESPERANDO_DESAMBIGUACION
                return RespuestaDialogo(
                    texto=(
                        f"{self.sesion.socios[nombre].nombre_completo} tiene varios "
                        f"créditos activos:\n{formatear_lista_letras(resolucion_letra.candidatos)}"
                    ),
                    requiere_timeout=True,
                )
            assert resolucion_letra.letra_id is not None
            self.sesion.letras[nombre] = resolucion_letra.letra_id

        if isinstance(intencion, IntConsultarSocio | IntConsultarCuotas | IntConsultarCaja):
            return await self._ejecutar_consulta()
        return self._construir_confirmacion()

    async def _recibir_seleccion_socio(self, pendiente: SeleccionPendiente, texto: str) -> RespuestaDialogo:
        indice = parsear_seleccion(texto, len(pendiente.candidatos_socio))
        if indice is None:
            return RespuestaDialogo(
                texto=(f"No entendí tu selección.\n{formatear_lista_socios(pendiente.candidatos_socio)}"),
                requiere_timeout=True,
            )
        self.sesion.pendientes.popleft()
        elegido = pendiente.candidatos_socio[indice]
        detalle = await self.cliente.get_socio(elegido.id)
        self.sesion.socios[pendiente.etiqueta] = SocioResuelto(
            id=elegido.id, nombre_completo=elegido.nombre_completo, saldo=detalle.saldo
        )
        return await self._resolver_entidades_y_continuar()

    async def _recibir_seleccion_letra(self, pendiente: SeleccionPendiente, texto: str) -> RespuestaDialogo:
        indice = parsear_seleccion(texto, len(pendiente.candidatos_letra))
        if indice is None:
            return RespuestaDialogo(
                texto=(f"No entendí tu selección.\n{formatear_lista_letras(pendiente.candidatos_letra)}"),
                requiere_timeout=True,
            )
        self.sesion.pendientes.popleft()
        elegido = pendiente.candidatos_letra[indice]
        self.sesion.letras[pendiente.etiqueta] = elegido.letra_id
        return await self._resolver_entidades_y_continuar()

    # ── Confirmación y ejecución ─────────────────────────────────────────────

    def _construir_confirmacion(self) -> RespuestaDialogo:
        assert self.sesion.intencion is not None
        texto = construir_resumen(self.sesion.intencion, self.sesion.socios, self.sesion.letras)
        self.sesion.resumen_texto = texto
        self.sesion.estado = EstadoDialogo.ESPERANDO_CONFIRMACION
        return RespuestaDialogo(texto=texto, requiere_timeout=True)

    # ── Consultas ────────────────────────────────────────────────────────────

    async def _ejecutar_consulta(self) -> RespuestaDialogo:
        intencion = self.sesion.intencion
        assert intencion is not None

        try:
            if isinstance(intencion, IntConsultarCaja):
                texto, pdf_bytes, nombre_pdf = await self._consultar_caja(), None, None
            elif isinstance(intencion, IntConsultarSocio):
                texto, pdf_bytes, nombre_pdf = await self._consultar_socio(intencion), None, None
            else:
                assert isinstance(intencion, IntConsultarCuotas)
                texto, pdf_bytes, nombre_pdf = await self._consultar_cuotas(intencion)
        except ApiError as exc:
            self._reset_operacion()
            self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
            return RespuestaDialogo(texto=exc.mensaje, cancelar_timeout=True)

        self._reset_operacion()
        self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
        return RespuestaDialogo(
            texto=texto,
            documento_pdf=pdf_bytes,
            nombre_documento=nombre_pdf,
            cancelar_timeout=True,
        )

    async def _consultar_caja(self) -> str:
        caja = await self.cliente.get_caja()
        return (
            f"Saldo en caja: {formatear_monto(caja.saldo_en_caja)}\n"
            f"Fondo administrativo: {formatear_monto(caja.total_admin)}\n"
            f"Mora: {caja.porcentaje_mora:.1%}"
        )

    async def _consultar_socio(self, intencion: IntConsultarSocio) -> str:
        resuelto = self.sesion.socios[intencion.socio]
        detalle = await self.cliente.get_socio(resuelto.id)
        return (
            f"{resuelto.nombre_completo}\n"
            f"Saldo: {formatear_monto(detalle.saldo)}\n"
            f"Créditos activos: {detalle.creditos_activos}"
        )

    async def _consultar_cuotas(self, intencion: IntConsultarCuotas) -> tuple[str, bytes | None, str | None]:
        nombre_socio = self.sesion.socios[intencion.socio].nombre_completo
        letra_id = self.sesion.letras[intencion.socio]
        resp = await self.cliente.get_cuotas_pendientes(letra_id)

        if not resp.cuotas_pendientes:
            return (
                f"{nombre_socio} no tiene cuotas pendientes en la letra {letra_id}.",
                None,
                None,
            )

        texto = (
            f"{nombre_socio} — Letra {letra_id}\n"
            f"Deuda total actual: {formatear_monto(resp.deuda_total_actual)}\n"
            f"Cuotas pendientes: {len(resp.cuotas_pendientes)}"
        )
        pdf_bytes = generar_pdf_tabla_cuotas(letra_id, resp.cuotas_pendientes, resp.deuda_total_actual)
        return texto, pdf_bytes, nombre_archivo_cuotas(letra_id)

    async def _ejecutar_operacion(self) -> tuple[bytes, str]:
        intencion = self.sesion.intencion
        key = self.sesion.idempotency_key
        assert intencion is not None
        assert key is not None

        if isinstance(intencion, IntRegAporte):
            body_aporte = AportesRequest(
                recibi_de_id=self.sesion.socios[intencion.recibi_de].id,
                aportes=[
                    AporteReqItem(socio_id=self.sesion.socios[a.nombre].id, monto=a.monto)
                    for a in intencion.aportes
                ],
            )
            resp_aporte = await self.cliente.registrar_aportes(body_aporte, key)
            datos = recibo_desde_aportes(resp_aporte)
        elif isinstance(intencion, IntRegRetiro):
            body_retiro = RetirosRequest(
                socio_id=self.sesion.socios[intencion.socio].id, monto=intencion.monto
            )
            resp_retiro = await self.cliente.registrar_retiro(body_retiro, key)
            datos = recibo_desde_retiro(resp_retiro)
        elif isinstance(intencion, IntRegPago):
            body_pago = PagosRequest(
                recibi_de_id=self.sesion.socios[intencion.recibi_de].id,
                pagos=self._pago_req_items(intencion.pagos),
            )
            resp_pago = await self.cliente.registrar_pagos(body_pago, key)
            datos = recibo_desde_pagos(resp_pago)
        else:
            assert isinstance(intencion, IntRegCombinado)
            body_combinado = CombinadosRequest(
                recibi_de_id=self.sesion.socios[intencion.recibi_de].id,
                aportes=[
                    AporteReqItem(socio_id=self.sesion.socios[a.nombre].id, monto=a.monto)
                    for a in intencion.aportes
                ],
                pagos=self._pago_req_items(intencion.pagos),
            )
            resp_combinado = await self.cliente.registrar_combinado(body_combinado, key)
            datos = recibo_desde_combinado(resp_combinado)

        # Primero se intenta el PDF autoritativo generado por el API a partir
        # de las plantillas Excel del BGC-software. Si el API no lo tiene
        # (entorno sin LibreOffice) se cae al PDF simple de reportlab.
        pdf_bytes_api = await self.cliente.descargar_pdf_recibo(datos.recibo_id)
        pdf_bytes = pdf_bytes_api if pdf_bytes_api is not None else generar_pdf_recibo(datos)
        return pdf_bytes, nombre_archivo_recibo(datos.recibo_id)

    def _pago_req_items(self, pagos: list[PagoItem]) -> list[PagoReqItem]:
        return [
            PagoReqItem(
                socio_id=self.sesion.socios[p.nombre].id,
                letra_id=self.sesion.letras[p.nombre],
                n_cuotas=p.n_cuotas,
                abono_capital=p.abono_capital,
            )
            for p in pagos
        ]

    # ── Helpers de estado ─────────────────────────────────────────────────────

    def _quedarse_en_espera(self, texto: str) -> RespuestaDialogo:
        self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
        return RespuestaDialogo(texto=texto)

    def _cancelar(self, mensaje: str) -> RespuestaDialogo:
        self._reset_operacion()
        self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
        return RespuestaDialogo(texto=mensaje, cancelar_timeout=True)

    def _reset_operacion(self) -> None:
        self.sesion.intencion = None
        self.sesion.socios = {}
        self.sesion.letras = {}
        self.sesion.pendientes = deque()
        self.sesion.idempotency_key = None
        self.sesion.resumen_texto = None
        self.sesion.texto_acumulado = None


# ── Helpers de módulo ──────────────────────────────────────────────────────────


def _nombres_socios(intencion: Intencion) -> list[str]:
    nombres: list[str] = []
    if isinstance(intencion, IntRegAporte):
        nombres.append(intencion.recibi_de)
        nombres += [a.nombre for a in intencion.aportes]
    elif isinstance(intencion, IntRegRetiro):
        nombres.append(intencion.socio)
    elif isinstance(intencion, IntRegPago):
        nombres.append(intencion.recibi_de)
        nombres += [p.nombre for p in intencion.pagos]
    elif isinstance(intencion, IntRegCombinado):
        nombres.append(intencion.recibi_de)
        nombres += [a.nombre for a in intencion.aportes]
        nombres += [p.nombre for p in intencion.pagos]
    elif isinstance(intencion, IntConsultarSocio | IntConsultarCuotas):
        nombres.append(intencion.socio)
    return list(dict.fromkeys(nombres))


def _pagos_de(intencion: Intencion) -> list[PagoItem]:
    if isinstance(intencion, IntRegPago | IntRegCombinado):
        return intencion.pagos
    return []


def _nombres_letras(intencion: Intencion) -> list[tuple[str, str | None]]:
    vistos: dict[str, str | None] = {}
    for pago in _pagos_de(intencion):
        vistos.setdefault(pago.nombre, pago.letra_id_hint)
    if isinstance(intencion, IntConsultarCuotas):
        vistos.setdefault(intencion.socio, intencion.letra_id_hint)
    return list(vistos.items())


_PREGUNTAS_POR_CAMPO: dict[str, str] = {
    "monto": "¿Cuánto es?",
    "socio": "¿De qué socio se trata?",
    "recibi_de": "¿Quién trae el dinero?",
    "nombre": "¿De qué socio?",
    "nombre del socio aportante": "¿A nombre de qué socio va el aporte?",
    "aportes": "¿Qué aporte se está registrando (socio y monto)?",
    "pagos": "¿Qué pago se está registrando (socio, cuotas o abono)?",
    "n_cuotas": "¿Cuántas cuotas está pagando?",
    "abono_capital": "¿Cuánto abona a capital?",
    "letra_id_hint": "¿Sabes el número de letra del crédito?",
    "capital": "¿De cuánto es el crédito?",
    "socios": "¿A nombre de quién queda el crédito?",
}


def _pregunta_por_faltantes(intencion_detectada: str, campos: list[str]) -> str:
    preguntas = [_PREGUNTAS_POR_CAMPO.get(c, f"me falta {c}") for c in campos]
    encabezado = {
        "registrar_aporte": "Para registrar el aporte necesito un dato más:",
        "registrar_retiro": "Para registrar el retiro necesito un dato más:",
        "registrar_pago": "Para registrar el pago necesito un dato más:",
        "registrar_combinado": "Para armar el recibo combinado necesito un dato más:",
        "crear_credito": "Para el crédito necesito un dato más:",
        "consultar_socio": "Necesito un dato para consultar el socio:",
        "consultar_cuotas": "Necesito un dato para consultar las cuotas:",
    }.get(intencion_detectada, "Me falta un dato:")
    return f"{encabezado} {' '.join(preguntas)}"


def _normalizar(texto: str) -> str:
    return texto.strip().lower()


def _es_afirmacion(texto: str) -> bool:
    return _normalizar(texto) in _AFIRMACIONES


def _es_negacion(texto: str) -> bool:
    return _normalizar(texto) in _NEGACIONES

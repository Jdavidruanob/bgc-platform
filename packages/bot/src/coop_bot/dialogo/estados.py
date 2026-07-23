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
    AporteItem,
    IntAmbigua,
    IntAyuda,
    IntConsultarCaja,
    IntConsultarCreditos,
    IntConsultarCuotas,
    IntConsultarFamilia,
    IntConsultarSocio,
    IntCrearCredito,
    IntDesconocida,
    Intencion,
    IntIncompleta,
    IntLiquidacionLetra,
    IntListarSocios,
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
    CrearCreditoRequest,
    CreditoResumen,
    PagoReqItem,
    PagosRequest,
    RetirosRequest,
    SocioSearchItem,
)

from coop_bot.api.cliente import ApiClient, ApiError
from coop_bot.dialogo.ayuda import texto_ayuda
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
    ReciboData,
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

# Límite físico de las plantillas: máximo 6 aportes y 6 pagos por recibo.
_MAX_FILAS = 6

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
    # Plan resuelto de aportes/pagos (registrar_aporte/pago/combinado).
    plan: PlanRecibo | None = None
    actualizado_en: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RespuestaDialogo:
    texto: str
    requiere_timeout: bool = False
    cancelar_timeout: bool = False
    documento_pdf: bytes | None = None
    nombre_documento: str | None = None
    # Documentos adicionales (nombre, bytes) para respuestas con varios PDFs,
    # p. ej. las liquidaciones de varias letras a la vez.
    documentos: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass
class AporteResuelto:
    socio_id: int
    nombre_completo: str
    monto: int


@dataclass
class PagoResuelto:
    letra_id: int
    socio_id: int
    nombre_socio: str
    n_cuotas: int
    abono_capital: int


@dataclass
class PlanRecibo:
    """Operación normalizada y resuelta: aportes y pagos por letra, ya listos
    para el resumen y para armar la petición al API. Retiro y crear crédito NO
    usan plan (van por su cuenta)."""

    aportes: list[AporteResuelto] = field(default_factory=list)
    pagos: list[PagoResuelto] = field(default_factory=list)
    recibi_de_id: int = 0
    recibi_de_nombre: str = ""

    @property
    def es_combinado(self) -> bool:
        return bool(self.aportes) and bool(self.pagos)


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
        if isinstance(intencion, IntAyuda):
            self.sesion.texto_acumulado = None
            return self._quedarse_en_espera(texto_ayuda(intencion.tema))
        if not isinstance(
            intencion,
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
            | IntLiquidacionLetra,
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

        es_credito = isinstance(self.sesion.intencion, IntCrearCredito)
        try:
            if es_credito:
                texto_ok, pdf_bytes, nombre_pdf = await self._ejecutar_crear_credito()
            else:
                texto_ok = "Listo, aquí está tu comprobante."
                pdf_bytes, nombre_pdf = await self._ejecutar_operacion()
        except ApiError as exc:
            self._reset_operacion()
            self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
            return RespuestaDialogo(texto=exc.mensaje, cancelar_timeout=True)

        self.sesion.estado = EstadoDialogo.RESPONDIENDO
        self._reset_operacion()
        self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
        return RespuestaDialogo(
            texto=texto_ok,
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

        # Resolver la letra SOLO de los pagos que dan nombre pero no la letra
        # (ni "todas las letras"). Los pagos con letra explícita se resuelven en
        # la finalización vía el API (la letra es única, no requiere preguntar).
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

        if isinstance(
            intencion,
            IntConsultarSocio
            | IntConsultarCuotas
            | IntConsultarCaja
            | IntListarSocios
            | IntConsultarCreditos
            | IntConsultarFamilia
            | IntLiquidacionLetra,
        ):
            return await self._ejecutar_consulta()

        # Retiro y crear crédito van por su cuenta (no se combinan).
        if isinstance(intencion, IntCrearCredito | IntRegRetiro):
            return self._construir_confirmacion()

        # registrar_aporte / registrar_pago / registrar_combinado → plan
        return await self._finalizar_plan(intencion)

    async def _finalizar_plan(self, intencion: Intencion) -> RespuestaDialogo:
        aportes_items, pagos_items, recibi_de_nombre = _partes_registro(intencion)

        aportes: list[AporteResuelto] = []
        for item in aportes_items:
            socio = self.sesion.socios[item.nombre]
            if item.familia:
                fam = await self.cliente.get_familia(socio.id)
                for m in fam.miembros:
                    aportes.append(AporteResuelto(m.id, m.nombre_completo, item.monto))
            else:
                aportes.append(AporteResuelto(socio.id, socio.nombre_completo, item.monto))

        pagos: list[PagoResuelto] = []
        for pago in pagos_items:
            if pago.todas_las_letras:
                assert pago.nombre is not None
                socio = self.sesion.socios[pago.nombre]
                creditos = (await self.cliente.get_creditos_socio(socio.id)).creditos
                if not creditos:
                    return self._cancelar(f"{socio.nombre_completo} no tiene créditos activos.")
                for c in creditos:
                    pagos.append(PagoResuelto(c.letra_id, socio.id, socio.nombre_completo, pago.n_cuotas, 0))
            elif pago.letra_id_hint is not None:
                letra_id = _parsear_letra(pago.letra_id_hint)
                if letra_id is None:
                    return self._cancelar(f"No entendí la letra '{pago.letra_id_hint}'.")
                try:
                    credito = await self.cliente.get_credito(letra_id)
                except ApiError:
                    return self._cancelar(f"No encontré un crédito con la letra {letra_id}.")
                nombre_socio = credito.socios[0].nombre_completo if credito.socios else f"letra {letra_id}"
                socio_id = credito.socios[0].id if credito.socios else 0
                pagos.append(
                    PagoResuelto(letra_id, socio_id, nombre_socio, pago.n_cuotas, pago.abono_capital)
                )
            else:
                assert pago.nombre is not None
                socio = self.sesion.socios[pago.nombre]
                letra_id = self.sesion.letras[pago.nombre]
                pagos.append(
                    PagoResuelto(letra_id, socio.id, socio.nombre_completo, pago.n_cuotas, pago.abono_capital)
                )

        if len(aportes) > _MAX_FILAS or len(pagos) > _MAX_FILAS:
            return self._cancelar(_mensaje_limite(len(aportes), len(pagos)))

        recibi_de_id, recibi_de_nom = self._resolver_recibi_de(recibi_de_nombre, aportes, pagos)
        if recibi_de_id == 0:
            return self._cancelar("No pude identificar de quién se recibe el dinero.")

        self.sesion.plan = PlanRecibo(
            aportes=aportes,
            pagos=pagos,
            recibi_de_id=recibi_de_id,
            recibi_de_nombre=recibi_de_nom,
        )
        texto = _resumen_plan(self.sesion.plan)
        self.sesion.resumen_texto = texto
        self.sesion.estado = EstadoDialogo.ESPERANDO_CONFIRMACION
        return RespuestaDialogo(texto=texto, requiere_timeout=True)

    def _resolver_recibi_de(
        self,
        nombre: str | None,
        aportes: list[AporteResuelto],
        pagos: list[PagoResuelto],
    ) -> tuple[int, str]:
        if nombre and nombre in self.sesion.socios:
            s = self.sesion.socios[nombre]
            return s.id, s.nombre_completo
        if aportes:
            return aportes[0].socio_id, aportes[0].nombre_completo
        if pagos:
            return pagos[0].socio_id, pagos[0].nombre_socio
        return 0, ""

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
        documentos: list[tuple[str, bytes]] = []

        try:
            if isinstance(intencion, IntConsultarCaja):
                texto = await self._consultar_caja()
            elif isinstance(intencion, IntConsultarSocio):
                texto = await self._consultar_socio(intencion)
            elif isinstance(intencion, IntListarSocios):
                texto = await self._listar_socios()
            elif isinstance(intencion, IntConsultarCreditos):
                texto = await self._consultar_creditos(intencion)
            elif isinstance(intencion, IntConsultarFamilia):
                texto = await self._consultar_familia(intencion)
            elif isinstance(intencion, IntLiquidacionLetra):
                texto, documentos = await self._liquidacion_letras(intencion)
            else:
                assert isinstance(intencion, IntConsultarCuotas)
                texto, pdf_bytes, nombre_pdf = await self._consultar_cuotas(intencion)
                if pdf_bytes is not None and nombre_pdf is not None:
                    documentos.append((nombre_pdf, pdf_bytes))
        except ApiError as exc:
            self._reset_operacion()
            self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
            return RespuestaDialogo(texto=exc.mensaje, cancelar_timeout=True)

        self._reset_operacion()
        self.sesion.estado = EstadoDialogo.ESPERANDO_MENSAJE
        return RespuestaDialogo(texto=texto, documentos=documentos, cancelar_timeout=True)

    async def _consultar_caja(self) -> str:
        caja = await self.cliente.get_caja()
        return (
            f"💰 Saldo en caja: {formatear_monto(caja.saldo_en_caja)}\n\n"
            f"Administración total: {formatear_monto(caja.administracion_total)}\n"
            f"  • Papelería: {formatear_monto(caja.papeleria)}\n"
            f"  • Por mora: {formatear_monto(caja.mora_acumulada)}\n\n"
            f"Tasa de mora: {caja.porcentaje_mora:.1%}"
        )

    async def _consultar_socio(self, intencion: IntConsultarSocio) -> str:
        resuelto = self.sesion.socios[intencion.socio]
        detalle = await self.cliente.get_socio(resuelto.id)
        return (
            f"{resuelto.nombre_completo}\n"
            f"Saldo: {formatear_monto(detalle.saldo)}\n"
            f"Créditos activos: {detalle.creditos_activos}"
        )

    async def _listar_socios(self) -> str:
        resp = await self.cliente.listar_socios()
        if not resp.socios:
            return "No hay socios registrados."
        lineas = [f"{i}. {s.nombre_completo}" for i, s in enumerate(resp.socios, start=1)]
        return f"Socios ({len(resp.socios)}):\n" + "\n".join(lineas)

    async def _consultar_creditos(self, intencion: IntConsultarCreditos) -> str:
        resuelto = self.sesion.socios[intencion.socio]
        resp = await self.cliente.get_creditos_socio(resuelto.id)
        if not resp.creditos:
            return f"{resuelto.nombre_completo} no tiene créditos activos."
        lineas = [f"Créditos de {resuelto.nombre_completo}:"]
        for c in resp.creditos:
            lineas.append(
                f"• Letra {c.letra_id}: {formatear_monto(c.capital_original)}, "
                f"{c.n_cuotas_total} cuotas, {c.interes_tasa * 100:.2f}% mensual"
            )
        return "\n".join(lineas)

    async def _consultar_familia(self, intencion: IntConsultarFamilia) -> str:
        resuelto = self.sesion.socios[intencion.socio]
        resp = await self.cliente.get_familia(resuelto.id)
        if len(resp.miembros) <= 1:
            return f"{resuelto.nombre_completo} no tiene familia registrada (solo aparece él/ella)."
        total = sum(m.saldo for m in resp.miembros)
        lineas = [f"Familia de {resuelto.nombre_completo} ({len(resp.miembros)} socios):"]
        for m in resp.miembros:
            lineas.append(f"• {m.nombre_completo}: {formatear_monto(m.saldo)}")
        lineas.append(f"Saldo total de la familia: {formatear_monto(total)}")
        return "\n".join(lineas)

    async def _liquidacion_letras(
        self, intencion: IntLiquidacionLetra
    ) -> tuple[str, list[tuple[str, bytes]]]:
        documentos: list[tuple[str, bytes]] = []
        encontradas: list[int] = []
        no_encontradas: list[int] = []
        for letra in intencion.letras:
            pdf_bytes = await self.cliente.descargar_pdf_liquidacion_actual(letra)
            if pdf_bytes is None:
                no_encontradas.append(letra)
            else:
                documentos.append((f"Liquidacion_actual_letra_{letra}.pdf", pdf_bytes))
                encontradas.append(letra)

        if encontradas and not no_encontradas:
            if len(encontradas) == 1:
                texto = f"Aquí está la liquidación actual de la letra {encontradas[0]}."
            else:
                lista = ", ".join(str(letra) for letra in encontradas)
                texto = f"Aquí están las liquidaciones actuales de las letras {lista}."
        elif encontradas and no_encontradas:
            ok = ", ".join(str(letra) for letra in encontradas)
            faltan = ", ".join(str(letra) for letra in no_encontradas)
            texto = f"Aquí están las liquidaciones de las letras {ok}. No encontré crédito para: {faltan}."
        elif len(no_encontradas) == 1:
            texto = f"No encontré un crédito con la letra {no_encontradas[0]}."
        else:
            faltan = ", ".join(str(letra) for letra in no_encontradas)
            texto = f"No encontré créditos con esas letras: {faltan}."
        return texto, documentos

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
        """Ejecuta un retiro (por su cuenta) o un plan (aporte/pago/combinado)."""
        intencion = self.sesion.intencion
        key = self.sesion.idempotency_key
        assert key is not None

        if isinstance(intencion, IntRegRetiro):
            body_retiro = RetirosRequest(
                socio_id=self.sesion.socios[intencion.socio].id, monto=intencion.monto
            )
            resp_retiro = await self.cliente.registrar_retiro(body_retiro, key)
            datos = recibo_desde_retiro(resp_retiro)
        else:
            datos = await self._ejecutar_plan(key)

        # Primero se intenta el PDF autoritativo generado por el API a partir
        # de las plantillas Excel del BGC-software. Si el API no lo tiene
        # (entorno sin LibreOffice) se cae al PDF simple de reportlab.
        pdf_bytes_api = await self.cliente.descargar_pdf_recibo(datos.recibo_id)
        pdf_bytes = pdf_bytes_api if pdf_bytes_api is not None else generar_pdf_recibo(datos)
        return pdf_bytes, nombre_archivo_recibo(datos.recibo_id)

    async def _ejecutar_plan(self, key: str) -> ReciboData:
        plan = self.sesion.plan
        assert plan is not None
        aportes_req = [AporteReqItem(socio_id=a.socio_id, monto=a.monto) for a in plan.aportes]
        pagos_req = [
            PagoReqItem(
                socio_id=p.socio_id,
                letra_id=p.letra_id,
                n_cuotas=p.n_cuotas,
                abono_capital=p.abono_capital,
            )
            for p in plan.pagos
        ]

        if aportes_req and pagos_req:
            resp_c = await self.cliente.registrar_combinado(
                CombinadosRequest(recibi_de_id=plan.recibi_de_id, aportes=aportes_req, pagos=pagos_req),
                key,
            )
            return recibo_desde_combinado(resp_c)
        if pagos_req:
            resp_p = await self.cliente.registrar_pagos(
                PagosRequest(recibi_de_id=plan.recibi_de_id, pagos=pagos_req), key
            )
            return recibo_desde_pagos(resp_p)
        resp_a = await self.cliente.registrar_aportes(
            AportesRequest(recibi_de_id=plan.recibi_de_id, aportes=aportes_req), key
        )
        return recibo_desde_aportes(resp_a)

    async def _ejecutar_crear_credito(self) -> tuple[str, bytes | None, str | None]:
        intencion = self.sesion.intencion
        key = self.sesion.idempotency_key
        assert isinstance(intencion, IntCrearCredito)
        assert key is not None

        body = CrearCreditoRequest(
            socio_ids=[self.sesion.socios[n].id for n in intencion.socios],
            capital=intencion.capital,
            n_cuotas=intencion.n_cuotas,
            interes=intencion.interes,
        )
        resp = await self.cliente.crear_credito(body, key)

        cuota_capital = resp.tabla_amortizacion[0].valor_cuota if resp.tabla_amortizacion else 0
        primera_cuota_total = resp.tabla_amortizacion[0].cuota_mensual if resp.tabla_amortizacion else 0
        texto = (
            f"Crédito creado. Letra {resp.letra_id}.\n"
            f"Capital: {formatear_monto(resp.capital)}\n"
            f"{resp.n_cuotas} cuotas · interés {resp.interes * 100:.2f}% mensual\n"
            f"Cuota a capital: {formatear_monto(cuota_capital)} "
            f"(primera cuota total ~{formatear_monto(primera_cuota_total)})\n"
            f"Saldo en caja: {formatear_monto(resp.saldo_caja_nuevo)}"
        )

        pdf_bytes = await self.cliente.descargar_pdf_liquidacion(resp.letra_id)
        nombre_pdf = f"Liquidacion_letra_{resp.letra_id}.pdf" if pdf_bytes is not None else None
        return texto, pdf_bytes, nombre_pdf

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
        self.sesion.plan = None


# ── Helpers de módulo ──────────────────────────────────────────────────────────


def _partes_registro(
    intencion: Intencion,
) -> tuple[list[AporteItem], list[PagoItem], str | None]:
    """Normaliza aporte/pago/combinado en (aportes, pagos, recibi_de)."""
    if isinstance(intencion, IntRegAporte):
        return list(intencion.aportes), [], intencion.recibi_de
    if isinstance(intencion, IntRegPago):
        return [], list(intencion.pagos), intencion.recibi_de
    if isinstance(intencion, IntRegCombinado):
        return list(intencion.aportes), list(intencion.pagos), intencion.recibi_de
    return [], [], None


def _nombres_socios(intencion: Intencion) -> list[str]:
    nombres: list[str] = []
    if isinstance(intencion, IntRegRetiro):
        nombres.append(intencion.socio)
    elif isinstance(intencion, IntRegAporte | IntRegPago | IntRegCombinado):
        aportes, pagos, recibi_de = _partes_registro(intencion)
        if recibi_de:
            nombres.append(recibi_de)
        nombres += [a.nombre for a in aportes]
        # Solo pagos con nombre y sin letra explícita (o "todas las letras")
        # necesitan resolver el socio por nombre.
        for p in pagos:
            if p.nombre and (p.todas_las_letras or p.letra_id_hint is None):
                nombres.append(p.nombre)
    elif isinstance(intencion, IntCrearCredito):
        nombres += list(intencion.socios)
    elif isinstance(
        intencion,
        IntConsultarSocio | IntConsultarCuotas | IntConsultarCreditos | IntConsultarFamilia,
    ):
        nombres.append(intencion.socio)
    return list(dict.fromkeys(nombres))


def _nombres_letras(intencion: Intencion) -> list[tuple[str, str | None]]:
    """Pagos que dan nombre pero NO letra explícita ni 'todas las letras':
    hay que resolver socio → letra (puede requerir desambiguación)."""
    vistos: dict[str, str | None] = {}
    _, pagos, _ = _partes_registro(intencion)
    for pago in pagos:
        if pago.nombre and not pago.todas_las_letras and pago.letra_id_hint is None:
            vistos.setdefault(pago.nombre, None)
    if isinstance(intencion, IntConsultarCuotas):
        vistos.setdefault(intencion.socio, intencion.letra_id_hint)
    return list(vistos.items())


def _parsear_letra(hint: str) -> int | None:
    texto = hint.strip().lstrip("#").removeprefix("letra").strip()
    return int(texto) if texto.isdigit() else None


def _mensaje_limite(n_aportes: int, n_pagos: int) -> str:
    partes = []
    if n_aportes > _MAX_FILAS:
        partes.append(f"{n_aportes} aportes")
    if n_pagos > _MAX_FILAS:
        partes.append(f"{n_pagos} pagos")
    return (
        f"El recibo soporta máximo {_MAX_FILAS} aportes y {_MAX_FILAS} pagos. "
        f"Tienes {' y '.join(partes)}. Divídelo en varios recibos."
    )


def _resumen_plan(plan: PlanRecibo) -> str:
    lineas = [f"Recibí de: {plan.recibi_de_nombre}"]
    if plan.aportes:
        lineas.append("Aportes:")
        for a in plan.aportes:
            lineas.append(f"- {a.nombre_completo}: {formatear_monto(a.monto)}")
    if plan.pagos:
        lineas.append("Pagos:")
        for p in plan.pagos:
            if p.n_cuotas > 0:
                modo = f"{p.n_cuotas} cuota(s)"
            else:
                modo = f"abono a capital de {formatear_monto(p.abono_capital)}"
            lineas.append(f"- Letra {p.letra_id} ({p.nombre_socio}): {modo}")
    lineas.append("")
    lineas.append(PROMPT_CONFIRMACION)
    return "\n".join(lineas)


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

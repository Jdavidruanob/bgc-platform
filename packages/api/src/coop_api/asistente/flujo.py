"""Despachador del asistente: sin sesión, sin estado guardado — todo el
contexto de la conversación viaja en el `id` del botón que Meta devuelve
intacto (ver `coop_api.asistente.copy.MENU_PRINCIPAL` para el vocabulario de
ids). Cada turno se resuelve solo con el número que escribió y el socio ya
identificado por el router.

Guarda de privacidad central: `liq:letra:<n>` SIEMPRE se revalida contra los
créditos activos del socio antes de mandar nada. Si `<n>` no es suyo, se
trata exactamente igual que un id desconocido — nunca se confirma ni se
niega que la letra exista.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.utils.fecha import get_hoy
from coop_core.utils.formato import format_miles_colombian_int
from fastapi import BackgroundTasks

from coop_api.asistente import consultas, copy
from coop_api.asistente.entrada import MensajeEntrante
from coop_api.asistente.liquidacion import (
    ErrorLiquidacion,
    enviar_liquidacion_pdf,
    preparar_datos_liquidacion,
)
from coop_api.asistente.whatsapp_cliente import Boton, ClienteWhatsApp, Fila

logger = logging.getLogger(__name__)

_MAX_VENCIDAS_MOSTRADAS = 4
_MAX_LETRAS_EN_LISTA = 9  # + 1 fila "De todos" = 10, el máximo de Meta


def atender(
    db: DbConnection,
    cliente: ClienteWhatsApp,
    background: BackgroundTasks,
    numero_meta: str,
    socio: dict[str, Any],
    mensaje: MensajeEntrante,
) -> None:
    hoy = get_hoy()
    if mensaje.tipo == "boton":
        _atender_boton(db, cliente, background, numero_meta, socio, mensaje.boton_id, hoy)
        return
    if mensaje.tipo == "otro":
        _enviar_menu(cliente, numero_meta, copy.no_puedo_escuchar_audio())
        return
    _enviar_menu(cliente, numero_meta, copy.saludo(socio))


def _atender_boton(
    db: DbConnection,
    cliente: ClienteWhatsApp,
    background: BackgroundTasks,
    numero_meta: str,
    socio: dict[str, Any],
    boton_id: str,
    hoy: date,
) -> None:
    socio_id = int(socio["id"])

    if boton_id == "menu:aportes":
        saldo_fmt = format_miles_colombian_int(int(socio.get("saldo") or 0))
        _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.saldo_de_aportes(socio, saldo_fmt))
        return

    if boton_id == "menu:creditos":
        letras = consultas.letras_activas(db, socio_id)
        if not letras:
            _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.sin_creditos_activos(socio))
            return
        botones = [Boton(id=i, titulo=t) for i, t in copy.BOTONES_LIQUIDACION_SI_NO]
        cliente.enviar_botones(numero_meta, copy.mis_creditos(letras), botones)
        return

    if boton_id == "menu:pagos":
        _enviar_respuesta_con_seguimiento(cliente, numero_meta, _texto_proximos_pagos(db, socio, hoy))
        return

    if boton_id == "liq:no":
        _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.liquidacion_no_gracias(socio))
        return

    if boton_id == "liq:si":
        letras = consultas.letras_activas(db, socio_id)
        if not letras:
            _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.sin_creditos_activos(socio))
            return
        if len(letras) == 1:
            _enviar_liquidacion(db, cliente, background, numero_meta, letras[0], hoy)
            return
        _pedir_letra(cliente, numero_meta, letras)
        return

    if boton_id == "liq:todos":
        letras = consultas.letras_activas(db, socio_id)
        if not letras:
            _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.sin_creditos_activos(socio))
            return
        _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.preparando_liquidacion())
        for letra_id in letras:
            _enviar_liquidacion(db, cliente, background, numero_meta, letra_id, hoy, avisar=False)
        return

    if boton_id.startswith("liq:letra:"):
        letra_elegida = _parsear_letra(boton_id)
        letras = consultas.letras_activas(db, socio_id) if letra_elegida is not None else []
        if letra_elegida is None or letra_elegida not in letras:
            # Guarda de privacidad central: id manipulado, ajeno o de un
            # crédito ya saldado — se trata igual que un id desconocido.
            _enviar_menu(cliente, numero_meta, copy.opcion_no_reconocida(socio))
            return
        _enviar_liquidacion(db, cliente, background, numero_meta, letra_elegida, hoy)
        return

    if boton_id == "fin:otra":
        _enviar_menu(cliente, numero_meta, copy.pregunta_otra_consulta(socio))
        return

    if boton_id == "fin:no":
        cliente.enviar_texto(numero_meta, copy.despedida(socio))
        return

    _enviar_menu(cliente, numero_meta, copy.opcion_no_reconocida(socio))


def _parsear_letra(boton_id: str) -> int | None:
    try:
        return int(boton_id.removeprefix("liq:letra:"))
    except ValueError:
        return None


def _pedir_letra(cliente: ClienteWhatsApp, numero_meta: str, letras: list[int]) -> None:
    if len(letras) <= 2:
        botones = [Boton(id=f"liq:letra:{n}", titulo=f"Letra #{n}") for n in letras]
        botones.append(Boton(id="liq:todos", titulo="De todos"))
        cliente.enviar_botones(numero_meta, copy.elegir_credito(), botones)
        return
    filas = [Fila(id=f"liq:letra:{n}", titulo=f"Letra #{n}") for n in letras[:_MAX_LETRAS_EN_LISTA]]
    filas.append(Fila(id="liq:todos", titulo="De todos"))
    cliente.enviar_lista(numero_meta, copy.elegir_credito(), "Ver créditos", filas)


def _enviar_liquidacion(
    db: DbConnection,
    cliente: ClienteWhatsApp,
    background: BackgroundTasks,
    numero_meta: str,
    letra_id: int,
    hoy: date,
    *,
    avisar: bool = True,
) -> None:
    resultado = preparar_datos_liquidacion(db, letra_id)
    if isinstance(resultado, ErrorLiquidacion):
        _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.liquidacion_no_disponible())
        return
    if avisar:
        _enviar_respuesta_con_seguimiento(cliente, numero_meta, copy.preparando_liquidacion())
    background.add_task(
        enviar_liquidacion_pdf, cliente, numero_meta, letra_id, resultado, hoy.strftime("%d/%m/%Y")
    )


def _enviar_menu(cliente: ClienteWhatsApp, numero_meta: str, texto: str) -> None:
    botones = [Boton(id=i, titulo=t) for i, t in copy.MENU_PRINCIPAL]
    cliente.enviar_botones(numero_meta, texto, botones)


def _enviar_respuesta_con_seguimiento(cliente: ClienteWhatsApp, numero_meta: str, texto: str) -> None:
    """Cierre estándar de cada respuesta: además de contestar, ofrece seguir
    consultando o despedirse — así la conversación nunca se queda en el aire."""
    cuerpo = f"{texto}\n\n{copy.pregunta_algo_mas()}"
    botones = [Boton(id=i, titulo=t) for i, t in copy.BOTONES_ALGO_MAS]
    cliente.enviar_botones(numero_meta, cuerpo, botones)


def _fecha_larga(fecha_iso: str) -> str:
    return datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def _texto_proximos_pagos(db: DbConnection, socio: dict[str, Any], hoy: date) -> str:
    letras = consultas.letras_activas(db, int(socio["id"]))
    lineas: list[str] = [copy.encabezado_proximos_pagos(socio), ""]
    hubo_alguna = False

    for letra_id in letras:
        cuotas = consultas.cuotas_pendientes_de_letra(db, letra_id, hoy)
        vencidas = [c for c in cuotas if c["estado"] == "vencida"]
        futuras = [c for c in cuotas if c["estado"] != "vencida"]
        if not vencidas and not futuras:
            continue
        hubo_alguna = True

        for c in vencidas[:_MAX_VENCIDAS_MOSTRADAS]:
            fecha_venc = _fecha_larga(c["fecha_vencimiento"])
            lineas.append(
                copy.linea_cuota_vencida(
                    letra_id, c["nro_cuota"], c["cuota_total"], fecha_venc, c["mora_estimada"]
                )
            )
        restantes = len(vencidas) - _MAX_VENCIDAS_MOSTRADAS
        if restantes > 0:
            lineas.append(f"  …y {restantes} cuota(s) vencida(s) más")

        if futuras:
            proxima = futuras[0]
            fecha_prox = _fecha_larga(proxima["fecha_vencimiento"])
            lineas.append(
                copy.linea_proximo_pago(letra_id, proxima["nro_cuota"], proxima["cuota_total"], fecha_prox)
            )

    if not hubo_alguna:
        return copy.sin_pagos_pendientes(socio)
    return "\n".join(lineas)

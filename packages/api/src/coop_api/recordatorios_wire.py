"""Genera recordatorios de WhatsApp para cuotas que hoy cumplen su fecha de
pago y están por entrar en mora (ver ADR-010, sección "Flujo de
recordatorios"). Pensado para correr una vez al día desde un job externo vía
`POST /recordatorios/cuotas-proximas`.

Solo avisa cuotas que TODAVÍA no entraron en mora: la cuota vence hoy (o
venció hace pocos días, si el job arranca por primera vez) pero sigue dentro
de `DIAS_GRACIA_MORA` (ver `calculate_mora`). Una cuota que ya pasó esos días
de gracia no genera aviso aquí — ya está en mora, avisar ahora llegaría
tarde. La idempotencia la da `liquidaciones.notif_prev_enviada`: cada cuota
se marca al avisarla, así que aunque el job corra varias veces nunca se
duplica el aviso.

Un crédito puede tener varios socios (co-deudores, ver `socio_credito`): cada
uno recibe su propia notificación, igual que en `notificar_credito_nuevo` de
`notificaciones_wire.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from coop_core.db.connection import DbConnection
from coop_core.repositories.config_repo import ConfigRepository
from coop_core.repositories.creditos_repo import CreditosRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.repositories.notificaciones_repo import NotificacionesRepository
from coop_core.repositories.socios_repo import SociosRepository
from coop_core.services.amortization import DIAS_GRACIA_MORA, calculate_mora
from coop_core.utils.fecha import get_hoy
from coop_core.utils.formato import format_miles_colombian_int
from coop_core.utils.telefono import derivar_whatsapp_e164


def _primer_nombre(nombres: Any) -> str:
    partes = str(nombres or "").strip().split()
    return partes[0].capitalize() if partes else ""


def _fecha_larga(fecha_iso: str) -> str:
    return datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def _params_cuota(
    letra_id: int, nro_cuota: int, valor_cuota: int, fecha_vencimiento: str, tasa_mora: float
) -> dict[str, str]:
    f_venc = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
    f_mora = f_venc + timedelta(days=DIAS_GRACIA_MORA)
    monto_mora = calculate_mora(fecha_vencimiento, f_mora, valor_cuota, tasa_mora)
    return {
        "numero_cuota": str(nro_cuota),
        "numero_letra": str(letra_id),
        "fecha_pago_cuota": _fecha_larga(fecha_vencimiento),
        "fecha_mora": f_mora.strftime("%d/%m/%Y"),
        "monto_mora": f"${format_miles_colombian_int(monto_mora)}",
    }


def _mensaje(nombres: Any, p: dict[str, str]) -> str:
    nombre = _primer_nombre(nombres)
    saludo = f"Hola, {nombre} 👋" if nombre else "Hola 👋"
    return (
        f"{saludo}\n\n"
        f"Te informamos que la cuota #{p['numero_cuota']} de tu crédito con letra "
        f"#{p['numero_letra']} cumple su fecha de pago hoy, {p['fecha_pago_cuota']}, "
        "y entrará en mora dentro de 5 días.\n\n"
        f"Paga antes del {p['fecha_mora']} y ahórrate {p['monto_mora']}.\n\n"
        "Recuerda que puedes consultar tus datos, créditos y pagos conmigo en "
        "cualquier momento. Solo escribe «Hola» y te guiaré. 😊\n\n"
        "¡Feliz resto de día! ☀️"
    )


def generar_recordatorios_cuotas_proximas(db: DbConnection) -> int:
    """Encola un recordatorio por socio para cada cuota que hoy cumple su
    fecha de pago (o venció hace pocos días) y aún no fue avisada. Devuelve
    cuántas notificaciones se encolaron."""
    liquidaciones_repo = LiquidacionesRepository(db)
    creditos_repo = CreditosRepository(db)
    socios_repo = SociosRepository(db)
    notificaciones_repo = NotificacionesRepository(db)
    tasa_mora = float(ConfigRepository(db).get("porcentaje_mora") or "0.02")

    cuotas = liquidaciones_repo.find_cuotas_por_avisar_mora(get_hoy(), DIAS_GRACIA_MORA)
    encoladas = 0

    for cuota in cuotas:
        liquidacion_id = int(cuota["id"])
        letra_id = int(cuota["credito_letra"])
        params = _params_cuota(
            letra_id,
            int(cuota["nro_cuota"]),
            int(cuota["valor_cuota"]),
            str(cuota["fecha_vencimiento"]),
            tasa_mora,
        )
        detalle_json = json.dumps(params)

        for socio_id in creditos_repo.get_socio_ids(letra_id):
            socio = socios_repo.find_by_id(socio_id)
            if socio is None:
                continue
            numero = derivar_whatsapp_e164(socio.get("whatsapp_e164"), socio.get("celular"))
            if numero is None:
                continue
            texto = _mensaje(socio.get("nombres"), params)
            notificaciones_repo.create(
                socio_id,
                numero,
                texto,
                documento_tipo="recordatorio_cuota",
                documento_id=liquidacion_id,
                detalle=detalle_json,
                estado="pendiente",
            )
            encoladas += 1

        # Se marca avisada aunque ningún socio tuviera WhatsApp derivable, para
        # no reintentar esa misma cuota todos los días (idempotencia, ver ADR-010).
        liquidaciones_repo.marcar_notif_prev_enviada(liquidacion_id)

    return encoladas

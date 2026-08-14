from datetime import date, datetime, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

# La cuota vence, y si no se paga dentro de estos días de gracia, empieza a
# cobrar mora (ej: vence el 1, el 6 ya cobra). Igual que en BGC-software desde
# el commit b75ae39 — antes de eso ambos daban 1 mes de gracia, sin componer.
DIAS_GRACIA_MORA = 5


def calculate_mora(
    fecha_venc_str: str, hoy: date, valor_cuota: int, tasa_mora: float, dias_gracia: int = DIAS_GRACIA_MORA
) -> int:
    """Mora acumulada de una cuota, cobrada por cada mes completo de atraso
    (no es un cobro único): si vence el 1 de enero y se paga el 6 de julio,
    van 7 meses de atraso; si se paga antes del 6 de julio, son 6."""
    f_venc = datetime.strptime(fecha_venc_str, "%Y-%m-%d").date()
    f_limite = f_venc + timedelta(days=dias_gracia)
    if hoy < f_limite:
        return 0
    rd = relativedelta(hoy, f_limite)
    meses_atraso = rd.years * 12 + rd.months + 1
    return int(valor_cuota * tasa_mora * meses_atraso)


def round_installments(capital: int, n_cuotas: int) -> tuple[int, int]:
    for redondeo in [10000, 9000, 8000, 7000, 6000, 5000, 2000, 1000]:
        posible = round((capital / n_cuotas) / redondeo) * redondeo
        ultima = capital - posible * (n_cuotas - 1)
        if 10000 <= ultima <= posible * 1.5:
            return posible, ultima
    cuota_base = capital // n_cuotas
    return cuota_base, capital - cuota_base * (n_cuotas - 1)


def build_amortization_schedule(
    letra_id: int,
    capital: int,
    interes: float,
    n_cuotas: int,
    fecha_inicio: date,
) -> list[tuple[Any, ...]]:
    """
    Retorna lista de tuplas para INSERT INTO liquidaciones:
    (credito_letra, nro_cuota, fecha_vencimiento, valor_cuota, interes_mes, cuota_mensual, saldo_capital)
    """
    cuota_base, cuota_final = round_installments(capital, n_cuotas)
    rows: list[tuple[Any, ...]] = []
    saldo = capital
    for i in range(n_cuotas):
        nro = i + 1
        fecha_venc = fecha_inicio + relativedelta(months=+nro)
        cap_pago = cuota_final if i == n_cuotas - 1 else cuota_base
        int_mes = int(round(saldo * interes))
        cuota_mensual = int(cap_pago + int_mes)
        saldo_final = max(int(saldo - cap_pago), 0)
        rows.append(
            (
                letra_id,
                nro,
                fecha_venc.strftime("%Y-%m-%d"),
                int(cap_pago),
                int_mes,
                cuota_mensual,
                saldo_final,
            )
        )
        saldo = saldo_final
    return rows


def build_cuotas_pendientes_detalle(
    pendientes: list[dict[str, Any]], hoy: date, tasa_mora: float
) -> list[dict[str, Any]]:
    """A partir de las cuotas pendientes de un crédito (`LiquidacionesRepository
    .find_pending`), calcula la mora vigente y el estado de cada una. Devuelve
    dicts (no un modelo de coop_contracts) para que tanto el router HTTP como
    el asistente de WhatsApp reusen el mismo cálculo sin que coop-core dependa
    de coop-contracts."""
    detalle: list[dict[str, Any]] = []
    for c in pendientes:
        mora = calculate_mora(str(c["fecha_vencimiento"]), hoy, int(c["valor_cuota"]), tasa_mora)
        fv = datetime.strptime(str(c["fecha_vencimiento"]), "%Y-%m-%d").date()
        estado = "vencida" if fv < hoy else ("vigente" if fv == hoy else "futuro")
        detalle.append(
            {
                "nro_cuota": int(c["nro_cuota"]),
                "fecha_vencimiento": str(c["fecha_vencimiento"]),
                "valor_cuota": int(c["valor_cuota"]),
                "interes_mes": int(c["interes_mes"]),
                "cuota_mensual": int(c["cuota_mensual"]),
                "mora_estimada": mora,
                "cuota_total": int(c["cuota_mensual"]) + mora,
                "estado": estado,
            }
        )
    return detalle

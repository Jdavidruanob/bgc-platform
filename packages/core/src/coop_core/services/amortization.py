from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta


def calculate_mora(fecha_venc_str: str, hoy: date, valor_cuota: int, tasa_mora: float) -> int:
    from datetime import datetime

    f_venc = datetime.strptime(fecha_venc_str, "%Y-%m-%d").date()
    f_limite = f_venc + relativedelta(months=+1)
    return int(valor_cuota * tasa_mora) if hoy > f_limite else 0


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

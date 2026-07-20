"""Helpers compartidos por PagoService y CombinadoService."""
from datetime import date, datetime
from typing import Any

from coop_core.db.connection import DbConnection, DbCursor
from coop_core.repositories.auxiliar_repo import AuxiliarRepository
from coop_core.repositories.liquidaciones_repo import LiquidacionesRepository
from coop_core.services.amortization import calculate_mora


def prepare_cuotas(
    conn: DbConnection,
    socio_data: dict[str, Any],
    letra_id: int,
    n_cuotas: int,
    hoy: date,
    tasa_mora: float,
) -> dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT nro_cuota, valor_cuota, interes_mes, cuota_mensual,
               saldo_capital, fecha_vencimiento
        FROM liquidaciones
        WHERE credito_letra = %s AND fecha_pago IS NULL
        ORDER BY nro_cuota LIMIT %s
        """,
        (letra_id, n_cuotas),
    )
    filas = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    nombre = f"{socio_data['nombres']} {socio_data['apellidos']}"
    if len(filas) < n_cuotas:
        raise ValueError(
            f"No hay suficientes cuotas pendientes en la letra {letra_id} para {nombre}."
        )
    items: list[dict[str, Any]] = []
    mensajes: list[str] = []
    for raw in filas:
        fila = dict(zip(cols, raw))
        mora = calculate_mora(str(fila["fecha_vencimiento"]), hoy, int(fila["valor_cuota"]), tasa_mora)
        costo_base = int(fila["valor_cuota"]) + int(fila["interes_mes"])
        items.append({
            "nro": int(fila["nro_cuota"]),
            "monto_total": costo_base + mora,
            "monto_base": costo_base,
            "mora": mora,
            "cap": int(fila["valor_cuota"]),
            "int": int(fila["interes_mes"]),
        })
        mensajes.append(f"Cuota #{fila['nro_cuota']}")
    return {
        "tipo": "CUOTAS_MANUAL",
        "socio_data": socio_data,
        "letra_id": letra_id,
        "items": items,
        "mensajes": mensajes,
    }


def prepare_abono(
    liquidaciones: LiquidacionesRepository,
    socio_data: dict[str, Any],
    letra_id: int,
    dinero_abono: int,
    hoy: date,
    tasa_mora: float,
) -> dict[str, Any]:
    nombre = f"{socio_data['nombres']} {socio_data['apellidos']}"
    pendientes = liquidaciones.find_pending(letra_id)
    vencidas: list[dict[str, Any]] = []
    for cuota in pendientes:
        f_venc = datetime.strptime(str(cuota["fecha_vencimiento"]), "%Y-%m-%d").date()
        if f_venc >= hoy:
            break
        mora = calculate_mora(str(cuota["fecha_vencimiento"]), hoy, int(cuota["valor_cuota"]), tasa_mora)
        base = int(cuota["valor_cuota"]) + int(cuota["interes_mes"])
        vencidas.append({"data": cuota, "costo_total": base + mora, "monto_base": base, "mora": mora})

    temp = dinero_abono
    pagables = 0
    for v in vencidas:
        if temp >= v["costo_total"]:
            temp -= v["costo_total"]
            pagables += 1
        else:
            if pagables == 0:
                raise ValueError(
                    f"Abono insuficiente para {nombre} (Letra {letra_id}): "
                    "no cubre la primera cuota vencida."
                )
            raise ValueError(
                f"Abono incompleto en letra {letra_id} para {nombre}. "
                "El monto no alcanza para cubrir las cuotas vencidas parcialmente."
            )

    remanente = 0
    if temp > 0:
        deuda = liquidaciones.get_current_debt(letra_id)
        cap_vencidas = sum(int(v["data"]["valor_cuota"]) for v in vencidas[:pagables])
        deuda_futura = deuda - cap_vencidas
        remanente = min(temp, deuda_futura)

    mensajes = [f"Vencida #{v['data']['nro_cuota']}" for v in vencidas[:pagables]]
    if remanente > 0:
        mensajes.append("Abono Capital")
    return {
        "tipo": "ABONO_CASCADA",
        "socio_data": socio_data,
        "letra_id": letra_id,
        "vencidas": vencidas[:pagables],
        "capital_puro": remanente,
        "mensajes": mensajes,
    }


def execute_pago_op(
    cursor: DbCursor,
    liquidaciones: LiquidacionesRepository,
    auxiliar: AuxiliarRepository,
    op: dict[str, Any],
    recibo_id: int,
    fecha: str,
    saldo_caja: int,
    mora_total: int,
    pagos_para_recibo: dict[int, dict[str, Any]],
    reporte_global: dict[str, list[str]],
) -> tuple[int, int]:
    letra_id: int = op["letra_id"]
    socio_data: dict[str, Any] = op["socio_data"]
    nombre = f"{socio_data['nombres']} {socio_data['apellidos']}"
    if nombre not in reporte_global:
        reporte_global[nombre] = []
    reporte_global[nombre].extend(op["mensajes"])

    dict_recibo = pagos_para_recibo[letra_id]

    if op["tipo"] == "CUOTAS_MANUAL":
        items: list[dict[str, Any]] = op["items"]
        dict_recibo["nro_cuotas_pagadas_start"] = items[0]["nro"]
        dict_recibo["nro_cuotas_pagadas_end"] = items[-1]["nro"]
        for it in items:
            cursor.execute(
                """
                INSERT INTO detalle_recibo
                    (recibo_id, tipo_operacion, socio_id, credito_letra, nro_cuota, monto, abono_mora)
                VALUES (%s, 'pago_credito', %s, %s, %s, %s, %s)
                """,
                (recibo_id, socio_data["id"], letra_id, it["nro"], it["monto_total"], it["mora"]),
            )
            cursor.execute(
                """
                UPDATE liquidaciones SET fecha_pago = %s, interes_mora = %s, mora_aplicada = %s
                WHERE credito_letra = %s AND nro_cuota = %s
                """,
                (fecha, it["mora"], 1 if it["mora"] > 0 else 0, letra_id, it["nro"]),
            )
            saldo_caja += it["monto_base"]
            mora_total += it["mora"]
            dict_recibo["valor_capital_consolidado"] += it["cap"]
            dict_recibo["interes_consolidado"] += it["int"]
            dict_recibo["mora_consolidada"] += it["mora"]
            auxiliar.add(
                fecha=fecha, tipo="Pago Credito", socio=nombre,
                monto=it["monto_base"], saldo=saldo_caja,
                recibo=recibo_id, cuota=it["nro"], id_credito=str(letra_id),
            )

    elif op["tipo"] == "ABONO_CASCADA":
        vencidas: list[dict[str, Any]] = op["vencidas"]
        capital_puro: int = op["capital_puro"]
        for v in vencidas:
            nro = int(v["data"]["nro_cuota"])
            cursor.execute(
                """
                INSERT INTO detalle_recibo
                    (recibo_id, tipo_operacion, socio_id, credito_letra, nro_cuota, monto, abono_mora)
                VALUES (%s, 'pago_credito', %s, %s, %s, %s, %s)
                """,
                (recibo_id, socio_data["id"], letra_id, nro, v["costo_total"], v["mora"]),
            )
            cursor.execute(
                """
                UPDATE liquidaciones SET fecha_pago = %s, interes_mora = %s, mora_aplicada = %s
                WHERE credito_letra = %s AND nro_cuota = %s
                """,
                (fecha, v["mora"], 1 if v["mora"] > 0 else 0, letra_id, nro),
            )
            saldo_caja += v["monto_base"]
            mora_total += v["mora"]
            dict_recibo["valor_capital_consolidado"] += int(v["data"]["valor_cuota"])
            dict_recibo["interes_consolidado"] += int(v["data"]["interes_mes"])
            dict_recibo["mora_consolidada"] += v["mora"]
            auxiliar.add(
                fecha=fecha, tipo="Pago Credito", socio=nombre,
                monto=v["monto_base"], saldo=saldo_caja,
                recibo=recibo_id, cuota=nro, id_credito=str(letra_id),
            )
        if capital_puro > 0:
            cursor.execute(
                """
                INSERT INTO detalle_recibo
                    (recibo_id, tipo_operacion, socio_id, credito_letra, nro_cuota, monto)
                VALUES (%s, 'pago_credito', %s, %s, 0, %s)
                """,
                (recibo_id, socio_data["id"], letra_id, capital_puro),
            )
            saldo_caja += capital_puro
            liquidaciones.recalculate_amortization(letra_id, capital_puro)
            dict_recibo["valor_capital_consolidado"] += capital_puro
            auxiliar.add(
                fecha=fecha, tipo="Abono Capital", socio=nombre,
                monto=capital_puro, saldo=saldo_caja,
                recibo=recibo_id, cuota=0, id_credito=str(letra_id),
            )
        if vencidas:
            dict_recibo["nro_cuotas_pagadas_start"] = int(vencidas[0]["data"]["nro_cuota"])
            dict_recibo["nro_cuotas_pagadas_end"] = (
                "ABONO" if capital_puro > 0 else int(vencidas[-1]["data"]["nro_cuota"])
            )
        else:
            dict_recibo["nro_cuotas_pagadas_start"] = "ABONO"
            dict_recibo["nro_cuotas_pagadas_end"] = "CAPITAL"

    deuda = dict_recibo["saldo_capital_antes_pago"] - dict_recibo["valor_capital_consolidado"]
    dict_recibo["saldo_capital_despues_pago"] = max(0, int(deuda))
    return saldo_caja, mora_total

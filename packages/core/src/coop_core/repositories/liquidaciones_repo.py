from datetime import date, datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from coop_core.db.connection import DbConnection


class LiquidacionesRepository:
    def __init__(self, conn: DbConnection) -> None:
        self._conn = conn

    def save_all(self, cuotas: list[tuple[Any, ...]]) -> None:
        cursor = self._conn.cursor()
        cursor.executemany(
            """
            INSERT INTO liquidaciones
                (credito_letra, nro_cuota, fecha_vencimiento, valor_cuota,
                 interes_mes, cuota_mensual, saldo_capital)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            cuotas,
        )

    def get_total_cuotas(self, credito_letra: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT no_cuotas FROM creditos WHERE letra = %s", (credito_letra,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def find_pending(self, letra_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT nro_cuota, fecha_vencimiento, valor_cuota,
                   interes_mes, cuota_mensual, saldo_capital
            FROM liquidaciones
            WHERE credito_letra = %s AND fecha_pago IS NULL
            ORDER BY nro_cuota ASC
            """,
            (letra_id,),
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_current_debt(self, letra_id: int) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT valor_cuota, saldo_capital FROM liquidaciones
            WHERE credito_letra = %s AND fecha_pago IS NULL
            ORDER BY nro_cuota ASC LIMIT 1
            """,
            (letra_id,),
        )
        row = cursor.fetchone()
        if row:
            return int(row[0]) + int(row[1])
        cursor.execute(
            "SELECT saldo_capital FROM liquidaciones WHERE credito_letra = %s "
            "ORDER BY nro_cuota DESC LIMIT 1",
            (letra_id,),
        )
        last = cursor.fetchone()
        return int(last[0]) if last else 0

    def recalculate_amortization(self, letra_id: int, abono_capital: int) -> None:
        cursor = self._conn.cursor()
        hoy = date.today().strftime("%Y-%m-%d")

        cursor.execute(
            "SELECT capital, interes, no_cuotas, fecha_inicio FROM creditos WHERE letra = %s",
            (letra_id,),
        )
        credito = cursor.fetchone()
        if credito is None:
            return

        capital_original, tasa_interes, no_cuotas_originales, fecha_inicio_str = (
            int(credito[0]), float(credito[1]), int(credito[2]), str(credito[3])
        )

        cursor.execute(
            "SELECT SUM(valor_cuota) FROM liquidaciones "
            "WHERE credito_letra = %s AND fecha_pago IS NOT NULL",
            (letra_id,),
        )
        pagado_cuotas = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT SUM(monto) FROM detalle_recibo
            WHERE credito_letra = %s AND (
                (tipo_operacion = 'pago_credito' AND nro_cuota = 0)
                OR tipo_operacion = 'abono_capital'
            )
            """,
            (letra_id,),
        )
        pagado_abonos = int(cursor.fetchone()[0] or 0)

        saldo_real_nuevo = capital_original - pagado_cuotas - pagado_abonos

        if saldo_real_nuevo <= 0:
            cursor.execute(
                "DELETE FROM liquidaciones WHERE credito_letra = %s AND fecha_pago IS NULL",
                (letra_id,),
            )
            self._sync_no_cuotas(cursor, letra_id)
            return

        cursor.execute(
            "SELECT valor_cuota FROM liquidaciones WHERE credito_letra = %s AND nro_cuota = 1",
            (letra_id,),
        )
        row_base = cursor.fetchone()
        amortizacion_fija = int(row_base[0]) if row_base else (capital_original // no_cuotas_originales)

        cursor.execute(
            "SELECT id, valor_cuota FROM liquidaciones "
            "WHERE credito_letra = %s AND fecha_pago IS NULL AND fecha_vencimiento < %s",
            (letra_id, hoy),
        )
        vencidas = cursor.fetchall()
        capital_en_vencidas = sum(int(v[1]) for v in vencidas)
        capital_para_futuro = max(saldo_real_nuevo - capital_en_vencidas, 0)

        cursor.execute(
            "DELETE FROM liquidaciones "
            "WHERE credito_letra = %s AND fecha_pago IS NULL AND fecha_vencimiento >= %s",
            (letra_id, hoy),
        )

        if capital_para_futuro == 0:
            self._sync_no_cuotas(cursor, letra_id)
            return

        cursor.execute(
            "SELECT nro_cuota, fecha_vencimiento FROM liquidaciones "
            "WHERE credito_letra = %s ORDER BY nro_cuota DESC LIMIT 1",
            (letra_id,),
        )
        ultimo_reg = cursor.fetchone()

        nro_start = int(ultimo_reg[0]) + 1 if ultimo_reg else 1
        fecha_start = (
            datetime.strptime(str(ultimo_reg[1]), "%Y-%m-%d")
            if ultimo_reg
            else datetime.strptime(fecha_inicio_str[:10], "%Y-%m-%d")
        )

        nuevas_cuotas: list[tuple[Any, ...]] = []
        saldo_iter = capital_para_futuro
        while saldo_iter > 0:
            fecha_start = fecha_start + relativedelta(months=+1)
            cap_pago = min(saldo_iter, amortizacion_fija)
            int_mes = int((saldo_iter + capital_en_vencidas) * tasa_interes)
            cuota_total = cap_pago + int_mes
            saldo_final_row = (saldo_iter - cap_pago) + capital_en_vencidas
            nuevas_cuotas.append((
                letra_id, nro_start, fecha_start.strftime("%Y-%m-%d"),
                int(cap_pago), int(int_mes), int(cuota_total), int(saldo_final_row),
            ))
            saldo_iter -= cap_pago
            nro_start += 1

        cursor.executemany(
            """
            INSERT INTO liquidaciones
                (credito_letra, nro_cuota, fecha_vencimiento, valor_cuota, interes_mes,
                 cuota_mensual, saldo_capital, interes_mora, mora_aplicada,
                 notif_prev_enviada, notif_venc_enviada, fecha_pago)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, NULL)
            """,
            nuevas_cuotas,
        )
        self._sync_no_cuotas(cursor, letra_id)

    def _sync_no_cuotas(self, cursor: Any, letra_id: int) -> None:
        cursor.execute(
            "SELECT MAX(nro_cuota) FROM liquidaciones WHERE credito_letra = %s",
            (letra_id,),
        )
        nueva_ultima = cursor.fetchone()[0]
        if nueva_ultima:
            cursor.execute(
                "UPDATE creditos SET no_cuotas = %s WHERE letra = %s",
                (int(nueva_ultima), letra_id),
            )

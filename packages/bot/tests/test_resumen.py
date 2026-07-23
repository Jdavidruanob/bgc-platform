import pytest
from coop_bot.dialogo.entidades import SocioResuelto
from coop_bot.dialogo.estados import AporteResuelto, PagoResuelto, PlanRecibo, _resumen_plan
from coop_bot.dialogo.resumen import construir_resumen, formatear_monto
from coop_contracts.intenciones import IntConsultarCaja, IntRegRetiro

MARIA = SocioResuelto(id=3, nombre_completo="María López Herrera", saldo=250000)


def test_formatear_monto() -> None:
    assert formatear_monto(320000) == "$320.000"
    assert formatear_monto(80000) == "$80.000"
    assert formatear_monto(0) == "$0"


# ── construir_resumen: solo retiro y crear crédito ────────────────────────────


def test_resumen_retiro() -> None:
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=200000)
    socios = {"María López": MARIA}
    texto = construir_resumen(intencion, socios, {})
    assert "María López Herrera" in texto
    assert "$200.000" in texto
    assert "responde sí o no" in texto.lower()


def test_resumen_intencion_no_soportada_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="no soporta"):
        construir_resumen(IntConsultarCaja(intencion="consultar_caja"), {}, {})


# ── _resumen_plan: aportes, pagos y combinado (por letra) ─────────────────────


def test_resumen_plan_aporte() -> None:
    plan = PlanRecibo(
        aportes=[AporteResuelto(socio_id=1, nombre_completo="Pedro Antonio Gómez Ruiz", monto=80000)],
        recibi_de_id=1,
        recibi_de_nombre="Pedro Antonio Gómez Ruiz",
    )
    texto = _resumen_plan(plan)
    assert "Recibí de: Pedro Antonio Gómez Ruiz" in texto
    assert "$80.000" in texto
    assert texto.endswith("¿Confirmas esta operación? Responde sí o no.")


def test_resumen_plan_pago_por_cuotas() -> None:
    plan = PlanRecibo(
        pagos=[PagoResuelto(letra_id=450, socio_id=1, nombre_socio="Pedro", n_cuotas=2, abono_capital=0)],
        recibi_de_id=1,
        recibi_de_nombre="Pedro",
    )
    texto = _resumen_plan(plan)
    assert "Letra 450" in texto
    assert "2 cuota(s)" in texto


def test_resumen_plan_pago_por_abono_capital() -> None:
    plan = PlanRecibo(
        pagos=[PagoResuelto(letra_id=450, socio_id=1, nombre_socio="Pedro", n_cuotas=0, abono_capital=50000)],
        recibi_de_id=1,
        recibi_de_nombre="Pedro",
    )
    texto = _resumen_plan(plan)
    assert "abono a capital de $50.000" in texto


def test_resumen_plan_combinado() -> None:
    plan = PlanRecibo(
        aportes=[AporteResuelto(socio_id=1, nombre_completo="Pedro", monto=80000)],
        pagos=[PagoResuelto(letra_id=450, socio_id=1, nombre_socio="Pedro", n_cuotas=1, abono_capital=0)],
        recibi_de_id=1,
        recibi_de_nombre="Pedro",
    )
    texto = _resumen_plan(plan)
    assert "Aportes:" in texto
    assert "Pagos:" in texto
    assert "$80.000" in texto
    assert "Letra 450" in texto

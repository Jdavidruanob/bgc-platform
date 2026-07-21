import pytest
from coop_bot.dialogo.entidades import SocioResuelto
from coop_bot.dialogo.resumen import construir_resumen, formatear_monto
from coop_contracts.intenciones import (
    AporteItem,
    IntConsultarCaja,
    IntRegAporte,
    IntRegCombinado,
    IntRegPago,
    IntRegRetiro,
    PagoItem,
)

PEDRO = SocioResuelto(id=1, nombre_completo="Pedro Antonio Gómez Ruiz", saldo=320000)
MARIA = SocioResuelto(id=3, nombre_completo="María López Herrera", saldo=250000)


def test_formatear_monto() -> None:
    assert formatear_monto(320000) == "$320.000"
    assert formatear_monto(80000) == "$80.000"
    assert formatear_monto(0) == "$0"


def test_resumen_aporte() -> None:
    intencion = IntRegAporte(
        intencion="registrar_aporte",
        recibi_de="Pedro Gómez",
        aportes=[AporteItem(nombre="Pedro Gómez", monto=80000)],
    )
    socios = {"Pedro Gómez": PEDRO}
    texto = construir_resumen(intencion, socios, {})
    assert "Pedro Antonio Gómez Ruiz" in texto
    assert "$80.000" in texto
    assert "$320.000" in texto
    assert texto.endswith("¿Confirmas esta operación? Responde sí o no.")


def test_resumen_retiro() -> None:
    intencion = IntRegRetiro(intencion="registrar_retiro", socio="María López", monto=200000)
    socios = {"María López": MARIA}
    texto = construir_resumen(intencion, socios, {})
    assert "María López Herrera" in texto
    assert "$200.000" in texto
    assert "responde sí o no" in texto.lower()


def test_resumen_pago_por_cuotas() -> None:
    intencion = IntRegPago(
        intencion="registrar_pago",
        recibi_de="Pedro Gómez",
        pagos=[PagoItem(nombre="Pedro Gómez", letra_id_hint="450", n_cuotas=2, abono_capital=0)],
    )
    socios = {"Pedro Gómez": PEDRO}
    letras = {"Pedro Gómez": 450}
    texto = construir_resumen(intencion, socios, letras)
    assert "letra 450" in texto
    assert "2 cuota(s)" in texto


def test_resumen_pago_por_abono_capital() -> None:
    intencion = IntRegPago(
        intencion="registrar_pago",
        recibi_de="Pedro Gómez",
        pagos=[PagoItem(nombre="Pedro Gómez", letra_id_hint=None, n_cuotas=0, abono_capital=50000)],
    )
    socios = {"Pedro Gómez": PEDRO}
    letras = {"Pedro Gómez": 450}
    texto = construir_resumen(intencion, socios, letras)
    assert "abono a capital de $50.000" in texto


def test_resumen_combinado() -> None:
    intencion = IntRegCombinado(
        intencion="registrar_combinado",
        recibi_de="Pedro Gómez",
        aportes=[AporteItem(nombre="Pedro Gómez", monto=80000)],
        pagos=[PagoItem(nombre="Pedro Gómez", letra_id_hint="450", n_cuotas=1, abono_capital=0)],
    )
    socios = {"Pedro Gómez": PEDRO}
    letras = {"Pedro Gómez": 450}
    texto = construir_resumen(intencion, socios, letras)
    assert "Aportes:" in texto
    assert "Pagos:" in texto
    assert "$80.000" in texto
    assert "letra 450" in texto


def test_resumen_intencion_no_soportada_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="no soporta"):
        construir_resumen(IntConsultarCaja(intencion="consultar_caja"), {}, {})

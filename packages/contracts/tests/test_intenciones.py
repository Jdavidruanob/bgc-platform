import pytest
from pydantic import ValidationError

from coop_contracts.intenciones import (
    AporteItem,
    IntAmbigua,
    IntCrearCredito,
    IntDesconocida,
    IntIncompleta,
    IntRegAporte,
    IntRegCombinado,
    IntRegPago,
    IntRegRetiro,
    PagoItem,
)


class TestAporteItem:
    def test_monto_positivo(self):
        a = AporteItem(nombre="Pedro", monto=80000)
        assert a.monto == 80000

    def test_monto_cero_rechazado(self):
        with pytest.raises(ValidationError):
            AporteItem(nombre="Pedro", monto=0)

    def test_monto_negativo_rechazado(self):
        with pytest.raises(ValidationError):
            AporteItem(nombre="Pedro", monto=-1000)


class TestPagoItem:
    def test_n_cuotas_valido(self):
        p = PagoItem(nombre="Carlos", n_cuotas=2)
        assert p.n_cuotas == 2
        assert p.abono_capital == 0

    def test_abono_capital_valido(self):
        p = PagoItem(nombre="Carlos", abono_capital=300000)
        assert p.abono_capital == 300000

    def test_dual_rechazado(self):
        with pytest.raises(ValidationError, match="excluyentes"):
            PagoItem(nombre="Carlos", n_cuotas=2, abono_capital=100000)

    def test_ninguno_rechazado(self):
        with pytest.raises(ValidationError, match="Debe especificarse"):
            PagoItem(nombre="Carlos", n_cuotas=0, abono_capital=0)

    def test_letra_id_hint_opcional(self):
        p = PagoItem(nombre="Héctor", letra_id_hint="450", abono_capital=300000)
        assert p.letra_id_hint == "450"


class TestIntRegAporte:
    def test_valido(self):
        i = IntRegAporte(
            intencion="registrar_aporte",
            recibi_de="Pedro",
            aportes=[{"nombre": "Pedro", "monto": 80000}],
        )
        assert len(i.aportes) == 1

    def test_aportes_vacios_rechazados(self):
        with pytest.raises(ValidationError):
            IntRegAporte(intencion="registrar_aporte", recibi_de="Pedro", aportes=[])


class TestIntRegRetiro:
    def test_valido(self):
        i = IntRegRetiro(intencion="registrar_retiro", socio="Rosa", monto=150000)
        assert i.monto == 150000

    def test_monto_cero_rechazado(self):
        with pytest.raises(ValidationError):
            IntRegRetiro(intencion="registrar_retiro", socio="Rosa", monto=0)


class TestIntRegPago:
    def test_valido(self):
        i = IntRegPago(
            intencion="registrar_pago",
            recibi_de="Carlos",
            pagos=[{"nombre": "Carlos", "n_cuotas": 2}],
        )
        assert i.pagos[0].n_cuotas == 2


class TestIntRegCombinado:
    def test_valido(self):
        i = IntRegCombinado(
            intencion="registrar_combinado",
            recibi_de="Luz Marina",
            aportes=[{"nombre": "Luz Marina", "monto": 80000}],
            pagos=[{"nombre": "Luz Marina", "n_cuotas": 1}],
        )
        assert len(i.aportes) == 1

    def test_sin_operaciones_rechazado(self):
        with pytest.raises(ValidationError, match="al menos"):
            IntRegCombinado(
                intencion="registrar_combinado",
                recibi_de="Luz",
                aportes=[],
                pagos=[],
            )


class TestIntCrearCredito:
    def test_valido(self):
        i = IntCrearCredito(
            intencion="crear_credito",
            socios=["Pedro Gómez"],
            capital=2000000,
            n_cuotas=12,
        )
        assert i.capital == 2000000

    def test_capital_cero_rechazado(self):
        with pytest.raises(ValidationError):
            IntCrearCredito(intencion="crear_credito", socios=["Pedro"], capital=0, n_cuotas=12)

    def test_socios_vacios_rechazados(self):
        with pytest.raises(ValidationError):
            IntCrearCredito(intencion="crear_credito", socios=[], capital=1000000, n_cuotas=12)


class TestIntEspeciales:
    def test_incompleta(self):
        i = IntIncompleta(
            intencion="incompleta",
            intencion_detectada="registrar_aporte",
            campos_faltantes=["monto"],
            texto_original="Recibí a Pedro",
        )
        assert "monto" in i.campos_faltantes

    def test_desconocida(self):
        i = IntDesconocida(
            intencion="desconocida",
            texto_original="¿Cuándo es la próxima reunión?",
        )
        assert i.texto_original

    def test_ambigua(self):
        i = IntAmbigua(
            intencion="ambigua",
            posibles_intenciones=["registrar_aporte", "registrar_pago"],
            texto_original="Pedro pagó",
        )
        assert len(i.posibles_intenciones) == 2

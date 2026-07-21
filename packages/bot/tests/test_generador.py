import io

from coop_bot.pdf.generador import (
    generar_pdf_recibo,
    generar_pdf_tabla_cuotas,
    nombre_archivo_cuotas,
    nombre_archivo_recibo,
    recibo_desde_aportes,
)
from coop_contracts.respuestas import (
    AporteResultItem,
    AportesResponse,
    CuotaPendiente,
    SocioRef,
)
from pypdf import PdfReader


def _texto_pdf(contenido: bytes) -> str:
    reader = PdfReader(io.BytesIO(contenido))
    return "\n".join(page.extract_text() for page in reader.pages)


def _aportes_response() -> AportesResponse:
    return AportesResponse(
        recibo_id=47,
        fecha="2026-07-18",
        recibi_de=SocioRef(id=1, nombre_completo="Pedro Antonio Gómez Ruiz"),
        aportes=[
            AporteResultItem(
                socio_id=1,
                nombre_completo="Pedro Antonio Gómez Ruiz",
                monto=80000,
                saldo_anterior=320000,
                saldo_nuevo=400000,
                cobro_papeleria=False,
            )
        ],
        papeleria_cobrada=0,
        saldo_caja_nuevo=5990000,
    )


def test_recibo_desde_aportes_mapea_correctamente() -> None:
    datos = recibo_desde_aportes(_aportes_response())
    assert datos.recibo_id == 47
    assert datos.total == 80000
    assert datos.lineas[0].socio == "Pedro Antonio Gómez Ruiz"


def test_generar_pdf_recibo_no_esta_vacio_y_contiene_datos_clave() -> None:
    datos = recibo_desde_aportes(_aportes_response())
    pdf_bytes = generar_pdf_recibo(datos)

    assert len(pdf_bytes) > 0

    texto = _texto_pdf(pdf_bytes)
    assert "47" in texto
    assert "80.000" in texto


def test_generar_pdf_tabla_cuotas_no_esta_vacio() -> None:
    cuotas = [
        CuotaPendiente(
            nro_cuota=5,
            fecha_vencimiento="2026-08-01",
            valor_cuota=85000,
            interes_mes=23400,
            cuota_mensual=108400,
            mora_estimada=0,
            estado="vigente",
        )
    ]
    pdf_bytes = generar_pdf_tabla_cuotas(450, cuotas, deuda_total=1450000)

    assert len(pdf_bytes) > 0
    texto = _texto_pdf(pdf_bytes)
    assert "450" in texto
    assert "1.450.000" in texto


def test_nombres_de_archivo() -> None:
    assert nombre_archivo_recibo(47) == "recibo_47.pdf"
    assert nombre_archivo_cuotas(450) == "cuotas_letra_450.pdf"

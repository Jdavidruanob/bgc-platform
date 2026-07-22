"""Convierte xlsx a PDF invocando LibreOffice headless.

En producción `libreoffice-core` + `libreoffice-calc` vienen instalados en la
imagen Docker (ver Dockerfile). En desarrollo local hay que tenerlos disponibles
en el `PATH` como `soffice`. Cada conversión toma 2-3 s y arranca su propio
proceso; para el tráfico esperado (una operación cada tanto) es suficiente.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class PdfConversionError(RuntimeError):
    pass


_TIMEOUT_SEGUNDOS = 30


def xlsx_a_pdf(xlsx_bytes: bytes) -> bytes:
    """Convierte los bytes de un xlsx a los bytes de un PDF respetando el diseño.

    Se materializa el xlsx en un directorio temporal, se corre soffice, y se
    leen los bytes del PDF resultante. El directorio se borra al terminar.
    """
    if not xlsx_bytes:
        raise PdfConversionError("xlsx vacío")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise PdfConversionError("soffice/libreoffice no está en el PATH")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        xlsx_path = tmp_path / "recibo.xlsx"
        xlsx_path.write_bytes(xlsx_bytes)

        try:
            resultado = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(xlsx_path),
                ],
                capture_output=True,
                timeout=_TIMEOUT_SEGUNDOS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfConversionError("LibreOffice tardó demasiado (>30s)") from exc

        if resultado.returncode != 0:
            raise PdfConversionError(
                f"LibreOffice falló (exit={resultado.returncode}): "
                f"{resultado.stderr.decode(errors='ignore')[:200]}"
            )

        pdf_path = tmp_path / "recibo.pdf"
        if not pdf_path.exists():
            raise PdfConversionError("LibreOffice no generó recibo.pdf")

        return pdf_path.read_bytes()

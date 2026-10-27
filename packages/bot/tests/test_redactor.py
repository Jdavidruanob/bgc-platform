"""Tests del redactor de avisos al operador: el LLM puede cambiar el tono,
nunca los datos."""

from __future__ import annotations

import asyncio
from datetime import datetime

from coop_bot.notificaciones import redactor
from coop_bot.notificaciones.redactor import conserva_hechos, redactar

ORIGINAL = (
    "🔔 Recordatorios de cuota próxima a vencer:\n"
    "• Te informo que le avisé a Ana Pérez que la cuota #3 del crédito #45 vence pronto "
    "y entra en mora el 2026-11-02."
)
NOMBRES = ["Ana Pérez"]
BIEN = (
    "Buenos días Álvaro ☀️ Ya le recordé a Ana Pérez que la cuota #3 del crédito #45 "
    "entra en mora el 2026-11-02."
)


class _Falso:
    def __init__(self, respuesta: str | None = None, error: Exception | None = None) -> None:
        self.respuesta, self.error = respuesta, error
        self.sistema = ""

    async def completar(self, sistema: str, usuario: str) -> str | None:
        self.sistema = sistema
        if self.error:
            raise self.error
        return self.respuesta


async def test_usa_el_texto_del_llm_si_conserva_los_datos() -> None:
    llm = _Falso(BIEN)
    assert await redactar(ORIGINAL, llm, NOMBRES, "Álvaro", datetime(2026, 10, 28, 9)) == BIEN
    assert "Álvaro" in llm.sistema and "mañana" in llm.sistema


async def test_si_el_llm_cambia_un_numero_se_usa_el_texto_fijo() -> None:
    malo = BIEN.replace("#45", "#54")
    assert await redactar(ORIGINAL, _Falso(malo), NOMBRES) == ORIGINAL


async def test_si_el_llm_pierde_un_socio_se_usa_el_texto_fijo() -> None:
    assert await redactar(ORIGINAL, _Falso(BIEN.replace("Ana Pérez", "Ana")), NOMBRES) == ORIGINAL


async def test_si_el_llm_falla_se_usa_el_texto_fijo() -> None:
    assert await redactar(ORIGINAL, _Falso(error=RuntimeError("caído")), NOMBRES) == ORIGINAL


async def test_respuesta_vacia_usa_el_texto_fijo() -> None:
    assert await redactar(ORIGINAL, _Falso("  "), NOMBRES) == ORIGINAL


async def test_sin_llm_usa_el_texto_fijo() -> None:
    assert await redactar(ORIGINAL, None, NOMBRES) == ORIGINAL


async def test_si_el_llm_tarda_se_usa_el_texto_fijo(monkeypatch) -> None:
    class _Lento:
        async def completar(self, sistema: str, usuario: str) -> str | None:
            await asyncio.sleep(1)
            return BIEN

    monkeypatch.setattr(redactor, "_TIMEOUT_SEGUNDOS", 0.01)
    assert await redactar(ORIGINAL, _Lento(), NOMBRES) == ORIGINAL


async def test_saludo_de_tarde_y_noche_sin_nombre() -> None:
    llm = _Falso(BIEN)
    await redactar(ORIGINAL, llm, NOMBRES, None, datetime(2026, 10, 28, 15))
    assert "tarde" in llm.sistema and "()" not in llm.sistema
    await redactar(ORIGINAL, llm, NOMBRES, None, datetime(2026, 10, 28, 21))
    assert "noche" in llm.sistema


def test_conserva_hechos_exige_codigo_de_error() -> None:
    original = "• Luis Gómez: su comprobante — error 131042"
    assert conserva_hechos(original, "Luis Gómez no lo recibió (error 131042)", ["Luis Gómez"])
    assert not conserva_hechos(original, "Luis Gómez no lo recibió", ["Luis Gómez"])

"""Cliente NLU: transcripción de texto -> `Intencion` estructurada vía OpenAI Chat."""

from __future__ import annotations

import json
from importlib import resources

from coop_contracts.intenciones import (
    IntDesconocida,
    Intencion,
)
from openai import AsyncOpenAI
from pydantic import TypeAdapter, ValidationError

_INTENCION_ADAPTER: TypeAdapter[Intencion] = TypeAdapter(Intencion)


def _cargar_prompt_sistema() -> str:
    return resources.files("coop_bot.nlu").joinpath("prompt_sistema.txt").read_text(encoding="utf-8")


class LlmClient:
    def __init__(self, api_key: str, modelo: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._modelo = modelo
        self._prompt_sistema = _cargar_prompt_sistema()

    async def interpretar(self, texto: str) -> Intencion:
        respuesta = await self._client.chat.completions.create(
            model=self._modelo,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._prompt_sistema},
                {"role": "user", "content": texto},
            ],
        )
        contenido = respuesta.choices[0].message.content
        return self._parsear(contenido, texto)

    def _parsear(self, contenido: str | None, texto_original: str) -> Intencion:
        if contenido is None:
            return IntDesconocida(intencion="desconocida", texto_original=texto_original)
        try:
            datos = json.loads(contenido)
            return _INTENCION_ADAPTER.validate_python(datos)
        except (json.JSONDecodeError, ValidationError):
            return IntDesconocida(intencion="desconocida", texto_original=texto_original)

"""Cliente de transcripción de audio (OpenAI Whisper)."""

from __future__ import annotations

import io

from openai import AsyncOpenAI


class WhisperClient:
    def __init__(self, api_key: str, modelo: str = "whisper-1") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._modelo = modelo

    async def transcribir(self, audio_bytes: bytes, filename: str = "audio.oga") -> str:
        archivo = io.BytesIO(audio_bytes)
        archivo.name = filename
        transcripcion = await self._client.audio.transcriptions.create(
            model=self._modelo,
            file=archivo,
            language="es",
        )
        return transcripcion.text

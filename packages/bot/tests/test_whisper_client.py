from types import SimpleNamespace
from unittest.mock import AsyncMock

from coop_bot.nlu.whisper_client import WhisperClient
from pytest_mock import MockerFixture


async def test_transcribir_devuelve_el_texto(mocker: MockerFixture) -> None:
    mock_openai_cls = mocker.patch("coop_bot.nlu.whisper_client.AsyncOpenAI")
    mock_instancia = mock_openai_cls.return_value
    mock_instancia.audio.transcriptions.create = AsyncMock(
        return_value=SimpleNamespace(text="Le recibí a Pedro Gómez su aporte de ochenta mil")
    )

    cliente = WhisperClient(api_key="sk-test")
    texto = await cliente.transcribir(b"contenido-de-audio-falso", filename="nota.oga")

    assert texto == "Le recibí a Pedro Gómez su aporte de ochenta mil"
    mock_instancia.audio.transcriptions.create.assert_awaited_once()
    _, kwargs = mock_instancia.audio.transcriptions.create.call_args
    assert kwargs["model"] == "whisper-1"
    assert kwargs["language"] == "es"


async def test_transcribir_usa_el_modelo_configurado(mocker: MockerFixture) -> None:
    mock_openai_cls = mocker.patch("coop_bot.nlu.whisper_client.AsyncOpenAI")
    mock_instancia = mock_openai_cls.return_value
    mock_instancia.audio.transcriptions.create = AsyncMock(return_value=SimpleNamespace(text="texto"))

    cliente = WhisperClient(api_key="sk-test", modelo="whisper-otro")
    await cliente.transcribir(b"audio")

    _, kwargs = mock_instancia.audio.transcriptions.create.call_args
    assert kwargs["model"] == "whisper-otro"

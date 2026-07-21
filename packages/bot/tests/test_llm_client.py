import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from coop_bot.nlu.llm_client import LlmClient
from pytest_mock import MockerFixture


def _respuesta_openai(contenido: str | None):
    mensaje = SimpleNamespace(content=contenido)
    choice = SimpleNamespace(message=mensaje)
    return SimpleNamespace(choices=[choice])


def _mock_create(mocker: MockerFixture, contenido: str | None) -> AsyncMock:
    mock_openai_cls = mocker.patch("coop_bot.nlu.llm_client.AsyncOpenAI")
    mock_instancia = mock_openai_cls.return_value
    create = AsyncMock(return_value=_respuesta_openai(contenido))
    mock_instancia.chat.completions.create = create
    return create


async def test_interpretar_registrar_aporte(mocker: MockerFixture) -> None:
    contenido = json.dumps(
        {
            "intencion": "registrar_aporte",
            "recibi_de": "Pedro Gómez",
            "aportes": [{"nombre": "Pedro Gómez", "monto": 80000}],
        }
    )
    _mock_create(mocker, contenido)

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("Le recibí a Pedro Gómez su aporte de ochenta mil")

    assert intencion.intencion == "registrar_aporte"
    assert intencion.recibi_de == "Pedro Gómez"  # type: ignore[union-attr]


async def test_interpretar_registrar_retiro(mocker: MockerFixture) -> None:
    contenido = json.dumps(
        {"intencion": "registrar_retiro", "socio": "María López", "monto": 200000}
    )
    _mock_create(mocker, contenido)

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("María López retira doscientos mil")

    assert intencion.intencion == "registrar_retiro"


async def test_interpretar_incompleta(mocker: MockerFixture) -> None:
    contenido = json.dumps(
        {
            "intencion": "incompleta",
            "intencion_detectada": "registrar_aporte",
            "campos_faltantes": ["monto"],
            "texto_original": "le recibí a Pedro su aporte",
        }
    )
    _mock_create(mocker, contenido)

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("le recibí a Pedro su aporte")

    assert intencion.intencion == "incompleta"


async def test_interpretar_json_malformado_cae_a_desconocida(mocker: MockerFixture) -> None:
    _mock_create(mocker, "esto no es json")

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("mensaje raro")

    assert intencion.intencion == "desconocida"
    assert intencion.texto_original == "mensaje raro"  # type: ignore[union-attr]


async def test_interpretar_intencion_desconocida_en_json_cae_a_desconocida(
    mocker: MockerFixture,
) -> None:
    contenido = json.dumps({"intencion": "algo_que_no_existe"})
    _mock_create(mocker, contenido)

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("mensaje raro")

    assert intencion.intencion == "desconocida"


async def test_interpretar_campo_requerido_faltante_cae_a_desconocida(
    mocker: MockerFixture,
) -> None:
    contenido = json.dumps({"intencion": "registrar_retiro", "socio": "María López"})
    _mock_create(mocker, contenido)

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("mensaje raro")

    assert intencion.intencion == "desconocida"


async def test_interpretar_contenido_nulo_cae_a_desconocida(mocker: MockerFixture) -> None:
    _mock_create(mocker, None)

    cliente = LlmClient(api_key="sk-test")
    intencion = await cliente.interpretar("mensaje raro")

    assert intencion.intencion == "desconocida"


async def test_interpretar_usa_el_modelo_configurado(mocker: MockerFixture) -> None:
    create = _mock_create(mocker, json.dumps({"intencion": "consultar_caja"}))

    cliente = LlmClient(api_key="sk-test", modelo="gpt-4o")
    await cliente.interpretar("¿cómo va la caja?")

    _, kwargs = create.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["temperature"] == 0

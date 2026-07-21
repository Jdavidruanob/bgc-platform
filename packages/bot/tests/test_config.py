import pytest
from coop_bot.config import Config, ConfigError

ENV_COMPLETO = {
    "COOP_API_BASE_URL": "http://localhost:8001",
    "COOP_API_TOKEN": "mock-secret",
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "TELEGRAM_OPERADOR_CHAT_ID": "987654321",
    "OPENAI_API_KEY": "sk-test",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None) -> None:
    env = {**ENV_COMPLETO, **(overrides or {})}
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_desde_entorno_lee_todas_las_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    cfg = Config.desde_entorno()

    assert cfg.coop_api_base_url == "http://localhost:8001"
    assert cfg.coop_api_token == "mock-secret"
    assert cfg.telegram_bot_token == "123:abc"
    assert cfg.telegram_operador_chat_id == 987654321
    assert cfg.openai_api_key == "sk-test"
    assert cfg.log_level == "DEBUG"


def test_desde_entorno_log_level_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    cfg = Config.desde_entorno()

    assert cfg.log_level == "INFO"


@pytest.mark.parametrize("faltante", sorted(ENV_COMPLETO))
def test_desde_entorno_falla_si_falta_variable(
    monkeypatch: pytest.MonkeyPatch, faltante: str
) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv(faltante, raising=False)

    with pytest.raises(ConfigError):
        Config.desde_entorno()


def test_desde_entorno_chat_id_no_numerico(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {"TELEGRAM_OPERADOR_CHAT_ID": "no-es-un-numero"})

    with pytest.raises(ConfigError):
        Config.desde_entorno()


def test_desde_entorno_whatsapp_es_opcional(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("WHATSAPP_CLOUD_API_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)

    cfg = Config.desde_entorno()

    assert cfg.whatsapp_cloud_api_token is None
    assert cfg.whatsapp_phone_number_id is None


def test_desde_entorno_whatsapp_se_lee_si_esta_presente(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")

    cfg = Config.desde_entorno()

    assert cfg.whatsapp_cloud_api_token == "meta-token"
    assert cfg.whatsapp_phone_number_id == "1234567890"

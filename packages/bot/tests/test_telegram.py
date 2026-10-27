from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from coop_bot.adaptadores import telegram as bot_telegram
from coop_bot.config import Config
from coop_bot.dialogo.estados import EstadoDialogo, SesionDialogo
from coop_contracts.intenciones import IntConsultarCaja, IntCrearCredito
from coop_contracts.respuestas import (
    CajaEstado,
    EntregaPorAvisar,
    EntregasPorAvisarResponse,
    SocioDetalle,
    SocioSearchItem,
    SociosSearchResponse,
)
from telegram.error import TelegramError

OPERADOR_CHAT_ID = 999


def _build_config() -> Config:
    return Config(
        coop_api_base_url="http://localhost:8001",
        coop_api_token="mock-secret",
        telegram_bot_token="123:abc",
        telegram_operador_chat_ids=(OPERADOR_CHAT_ID,),
        openai_api_key="sk-test",
    )


def _contexto(chat_data: dict | None = None) -> MagicMock:
    context = MagicMock()
    context.chat_data = {} if chat_data is None else chat_data
    context.bot_data = {
        "config": _build_config(),
        "api_client": AsyncMock(),
        "llm_client": AsyncMock(),
        "whisper_client": AsyncMock(),
    }
    context.bot.send_message = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.get_chat = AsyncMock(side_effect=TelegramError("sin chat"))
    context.job_queue = MagicMock()
    context.job_queue.get_jobs_by_name.return_value = []
    return context


def _update(chat_id: int, texto: str | None = None, nombre: str = "Álvaro") -> MagicMock:
    update = MagicMock()
    update.effective_chat = SimpleNamespace(id=chat_id)
    update.effective_user = SimpleNamespace(first_name=nombre)
    update.message.text = texto
    update.message.voice = None
    return update


# ── Guardas ──────────────────────────────────────────────────────────────────


def test_es_operador_true_para_el_chat_configurado() -> None:
    context = _contexto()
    update = _update(OPERADOR_CHAT_ID)
    assert bot_telegram._es_operador(update, context) is True


def test_es_operador_false_para_otro_chat() -> None:
    context = _contexto()
    update = _update(chat_id=111)
    assert bot_telegram._es_operador(update, context) is False


# ── Sesión ───────────────────────────────────────────────────────────────────


def test_obtener_sesion_crea_una_nueva_si_no_existe() -> None:
    context = _contexto()
    sesion = bot_telegram._obtener_sesion(context, OPERADOR_CHAT_ID)
    assert sesion.chat_id == OPERADOR_CHAT_ID
    assert sesion.estado == EstadoDialogo.ESPERANDO_MENSAJE
    assert context.chat_data["sesion"] is sesion


def test_obtener_sesion_reutiliza_la_existente() -> None:
    sesion_existente = SesionDialogo(chat_id=OPERADOR_CHAT_ID, estado=EstadoDialogo.ESPERANDO_CONFIRMACION)
    context = _contexto(chat_data={"sesion": sesion_existente})
    sesion = bot_telegram._obtener_sesion(context, OPERADOR_CHAT_ID)
    assert sesion is sesion_existente


# ── on_text ──────────────────────────────────────────────────────────────────


async def test_on_text_ignora_mensajes_de_chats_no_autorizados() -> None:
    context = _contexto()
    update = _update(chat_id=111, texto="hola")

    await bot_telegram.on_text(update, context)

    context.bot.send_message.assert_not_called()


async def test_on_text_consulta_caja_responde_con_el_saldo() -> None:
    context = _contexto()
    context.bot_data["llm_client"].interpretar = AsyncMock(
        return_value=IntConsultarCaja(intencion="consultar_caja")
    )
    context.bot_data["api_client"].get_caja = AsyncMock(
        return_value=CajaEstado(saldo_en_caja=5830000, total_admin=270000, porcentaje_mora=0.02)
    )
    update = _update(OPERADOR_CHAT_ID, texto="¿cómo va la caja?")

    await bot_telegram.on_text(update, context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "$5.830.000" in kwargs["text"]


async def test_on_text_crear_credito_pide_confirmacion() -> None:
    context = _contexto()
    context.bot_data["llm_client"].interpretar = AsyncMock(
        return_value=IntCrearCredito(
            intencion="crear_credito", socios=["Carmenza Suárez"], capital=1200000, n_cuotas=12
        )
    )
    context.bot_data["api_client"].buscar_socios = AsyncMock(
        return_value=SociosSearchResponse(
            socios=[
                SocioSearchItem(
                    id=4,
                    nombres="Carmenza",
                    apellidos="Suárez Peña",
                    nombre_completo="Carmenza Suárez Peña",
                    score=0.95,
                )
            ]
        )
    )
    context.bot_data["api_client"].get_socio = AsyncMock(
        return_value=SocioDetalle(
            id=4, nombres="Carmenza", apellidos="Suárez Peña", celular="", saldo=180000, creditos_activos=0
        )
    )
    update = _update(OPERADOR_CHAT_ID, texto="crea un crédito para Carmenza, un millón a 12 cuotas")

    await bot_telegram.on_text(update, context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "Nuevo crédito" in kwargs["text"]


async def test_on_text_falla_llm_responde_mensaje_generico() -> None:
    context = _contexto()
    context.bot_data["llm_client"].interpretar = AsyncMock(side_effect=RuntimeError("boom"))
    update = _update(OPERADOR_CHAT_ID, texto="algo")

    await bot_telegram.on_text(update, context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "no pude interpretar" in kwargs["text"].lower()


async def test_saludo_usa_el_nombre_del_perfil() -> None:
    context = _contexto()
    update = _update(OPERADOR_CHAT_ID, texto="hola", nombre="Mary")

    await bot_telegram.on_text(update, context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "Hola Mary" in kwargs["text"]
    # El saludo no gasta el LLM
    context.bot_data["llm_client"].interpretar.assert_not_called()


async def test_ayuda_credito_explica_que_necesita() -> None:
    from coop_contracts.intenciones import IntAyuda

    context = _contexto()
    context.bot_data["llm_client"].interpretar = AsyncMock(
        return_value=IntAyuda(intencion="ayuda", tema="credito")
    )
    update = _update(OPERADOR_CHAT_ID, texto="quiero hacer un crédito, ¿qué necesitas?")

    await bot_telegram.on_text(update, context)

    context.bot.send_message.assert_awaited_once()
    _, kwargs = context.bot.send_message.call_args
    assert "crédito" in kwargs["text"].lower()
    assert "cuotas" in kwargs["text"].lower()


# ── Aviso de la entrega real por WhatsApp ───────────────────────────────────


def _entregas(*resultados: str) -> EntregasPorAvisarResponse:
    return EntregasPorAvisarResponse(
        entregas=[
            EntregaPorAvisar(id=i + 1, socio_nombre="Pedro Gómez", resultado=r, error="131042: pago")
            for i, r in enumerate(resultados)
        ]
    )


async def test_avisar_entregas_envia_a_telegram_y_marca_avisadas() -> None:
    context = _contexto()
    context.bot_data["api_client"].get_entregas_por_avisar = AsyncMock(return_value=_entregas("failed"))

    await bot_telegram._avisar_entregas(context)

    context.bot.send_message.assert_awaited_once()
    texto = context.bot.send_message.call_args.kwargs["text"]
    assert "NO les llegó" in texto and "método de pago" in texto
    context.bot_data["api_client"].marcar_entregas_avisadas.assert_awaited_once_with([1])


async def test_avisar_entregas_redactado_por_el_llm_saluda_al_operador() -> None:
    context = _contexto()
    context.bot.get_chat = AsyncMock(return_value=MagicMock(first_name="Álvaro"))
    context.bot_data["api_client"].get_entregas_por_avisar = AsyncMock(return_value=_entregas("delivered"))
    context.bot_data["llm_client"].completar = AsyncMock(
        return_value="Hola Álvaro 👋 A Pedro Gómez ya le llegó su comprobante."
    )

    await bot_telegram._avisar_entregas(context)

    texto = context.bot.send_message.call_args.kwargs["text"]
    assert texto.endswith("Hola Álvaro 👋 A Pedro Gómez ya le llegó su comprobante.")
    sistema = context.bot_data["llm_client"].completar.call_args.args[0]
    assert "Álvaro" in sistema


async def test_avisar_entregas_sin_novedades_no_envia_nada() -> None:
    context = _contexto()
    context.bot_data["api_client"].get_entregas_por_avisar = AsyncMock(return_value=_entregas())

    await bot_telegram._avisar_entregas(context)

    context.bot.send_message.assert_not_called()
    context.bot_data["api_client"].marcar_entregas_avisadas.assert_not_called()


async def test_avisar_entregas_no_marca_si_telegram_falla() -> None:
    """Si el aviso no salió, queda pendiente para el siguiente ciclo."""
    context = _contexto()
    context.bot_data["api_client"].get_entregas_por_avisar = AsyncMock(return_value=_entregas("delivered"))
    context.bot.send_message = AsyncMock(side_effect=TelegramError("sin red"))

    await bot_telegram._avisar_entregas(context)

    context.bot_data["api_client"].marcar_entregas_avisadas.assert_not_called()

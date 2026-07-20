# 08 — Onboarding Dev B

> Este documento es autocontenido. No necesitas acceso a más código ni a datos reales para arrancar.

---

## ¿Qué construyes?

Construyes el bot de mensajería de la cooperativa. El bot recibe mensajes de voz y texto del operador (el tesorero), entiende qué operación quiere hacer, pide confirmación, y ejecuta la operación llamando a una API REST.

**Tu paquete:** `packages/bot/` — todo lo que ocurre entre el mensaje del usuario y la llamada HTTP.

**Tu contrato:** la API que consumes está especificada en `docs/05-contrato-api.md` y los schemas en `packages/contracts/`. Para desarrollar y probar, nunca necesitas ver la implementación interna de la API; solo tienes el mock server (ver §Levantar el mock server).

---

## Lo que NO tienes que construir

- La lógica financiera (cómo se calculan cuotas, saldos, mora) — eso lo hace el backend.
- La API REST — ya está hecha o la está haciendo Dev A.
- La aplicación de escritorio.
- La base de datos.

---

## Flujo completo de una operación

```
Operador
  │
  │ 🎤 nota de voz (Telegram)
  ▼
[Adaptador Telegram]
  │ descarga audio
  ▼
[Cliente Whisper]
  │ transcripción en español
  ▼
[Módulo NLU]  ──── llama a OpenAI Chat API ────
  │ JSON de intención (schemas en packages/contracts/)
  ▼
[Resolución de entidades]
  │ nombres → IDs de socios (llama a GET /socios?q=)
  │ si hay ambigüedad → pregunta al operador
  ▼
[Construcción del resumen]
  │ texto legible con nombres reales, montos, saldos
  ▼
[Envío al operador para confirmación]
  │
  │ Operador responde "sí" o "no"
  │
  ├── "no" o timeout → cancela, nada se guarda
  │
  └── "sí"
        ▼
      [Cliente API]  ──── POST /operaciones/... ────
        │ response con datos del comprobante
        ▼
      [Generador PDF]
        │
        ▼
      [Envío del PDF al operador]
```

---

## Estructura de carpetas del bot

```
packages/bot/
├── pyproject.toml
└── src/
    └── coop_bot/
        ├── __init__.py
        ├── main.py                 Punto de entrada. Configura el bot de Telegram.
        ├── adaptadores/
        │   └── telegram.py         Recibe mensajes, envía respuestas y PDFs.
        ├── nlu/
        │   ├── whisper_client.py   Audio → texto.
        │   ├── llm_client.py       Texto → JSON de intención.
        │   └── prompt_sistema.txt  Prompt del sistema para el LLM.
        ├── dialogo/
        │   ├── estados.py          Máquina de estados del diálogo.
        │   ├── resumen.py          Construye el texto de confirmación.
        │   └── entidades.py        Resolución de nombres → socio_id.
        ├── api/
        │   └── cliente.py          Wraper sobre httpx. Llama a coop-api.
        ├── pdf/
        │   └── generador.py        Genera PDF de comprobante con reportlab.
        └── config.py               Lee variables de entorno.
```

---

## Levantar el mock server localmente

El mock server simula la API completa con datos ficticios. No necesitas Postgres ni Docker.

```bash
# 1. Clonar el repositorio (si no lo tienes)
git clone <repo-url>
cd tesoro

# 2. Instalar uv (si no lo tienes)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Instalar dependencias del workspace
uv sync

# 4. Levantar el mock server
uv run --package coop-contracts python -m coop_contracts.mock_server

# El mock server corre en: http://localhost:8001
# Documentación interactiva: http://localhost:8001/docs
```

El mock server responde con datos ficticios pero estructuralmente correctos (mismos schemas que la API real). Los socios del mock están definidos en `packages/contracts/src/coop_contracts/mock_data.py`.

---

## Variables de entorno necesarias para el bot

Crea `packages/bot/.env` (nunca hagas commit de este archivo):

```bash
# API
COOP_API_BASE_URL=http://localhost:8001   # mock server local
COOP_API_TOKEN=mock-secret                # token del mock (default)

# Telegram
TELEGRAM_BOT_TOKEN=<tu-token-de-@BotFather>
TELEGRAM_OPERADOR_CHAT_ID=<tu-chat-id>   # solo este chat puede usar el bot

# OpenAI
OPENAI_API_KEY=<tu-api-key>

# Opcionales
LOG_LEVEL=DEBUG
```

Para obtener `TELEGRAM_OPERADOR_CHAT_ID`: inicia una conversación con tu bot y visita `https://api.telegram.org/bot<TOKEN>/getUpdates`.

---

## Socios ficticios del mock server

Para tus pruebas, el mock server tiene estos socios (definidos en `packages/contracts/src/coop_contracts/mock_data.py`):

| ID | Nombre | Saldo | Créditos activos | WhatsApp |
|----|--------|-------|-----------------|----------|
| 1 | Pedro Antonio Gómez Ruiz | $320.000 | 1 (letra 450) | +573001234567 |
| 2 | Pedro Luis Gómez Castro | $150.000 | 0 | +573009876543 |
| 3 | María López Herrera | $250.000 | 0 | +573112223344 |
| 4 | Carmenza Suárez Peña | $180.000 | 0 | +573124445566 |
| 5 | Hernando Ruiz Vargas | $500.000 | 1 (letra 451) | +573201112233 |

> **Nota:** Los socios 1 y 2 son homónimos ("Pedro Gómez"). Cualquier búsqueda de "pedro" retorna ambos, lo que te permite probar el flujo de desambiguación (R-02 / R-05).

Saldo de caja del mock: **$5.830.000**

Token para el mock: `mock-secret` (valor por defecto; configurable con `API_SECRET_TOKEN`).

---

## Probar el trabajo end-to-end sin datos reales

### Opción 1: Test automatizado
```bash
uv run pytest packages/bot -v
```

Los tests en `packages/bot/tests/` usan el mock server (levantado como fixture en `conftest.py`) y simulan conversaciones completas.

### Opción 2: Manual con Telegram real

1. Levanta el mock server (`uv run --package coop-contracts python -m coop_contracts.mock_server`).
2. Levanta el bot en modo polling (no webhook):
   ```bash
   uv run --package coop-bot python -m coop_bot.main --modo=polling
   ```
3. Abre Telegram y envía una nota de voz con, por ejemplo:
   > "Le recibí a Pedro Gómez su aporte de ochenta mil"
4. El bot debe responder con el resumen de confirmación.
5. Responde "sí" y deberías recibir el PDF del recibo #1 (generado con datos ficticios).

### Opción 3: Test de integración programático

```bash
# Simula el flujo completo sin Telegram (llama directamente a los módulos)
uv run pytest packages/bot/tests/test_flujo_completo.py -v
```

---

## Schemas disponibles en `coop-contracts`

Importa así desde tu código:

```python
# Intenciones que el LLM produce (NLU → bot)
from coop_contracts.intenciones import (
    IntRegAporte, IntRegRetiro, IntRegPago, IntRegCombinado,
    IntCrearCredito,
    IntConsultarSocio, IntConsultarCuotas, IntConsultarCaja,
    IntDesconocida, IntIncompleta, IntAmbigua,
    Intencion,  # Union de todas las anteriores
)

# Schemas de request (lo que el bot envía a la API)
from coop_contracts.respuestas import (
    AportesRequest, RetirosRequest, PagosRequest, CombinadosRequest,
)

# Schemas de response (lo que la API devuelve al bot)
from coop_contracts.respuestas import (
    AportesResponse, RetiroResponse, PagosResponse, CombinadoResponse,
    SociosSearchResponse, SocioDetalle,
    CreditosResponse, CuotasPendientesResponse,
    CajaEstado, ErrorResponse,
)

# Interfaz de notificaciones (para implementar tus Notificadores)
from coop_contracts.notificador import Notificador, MockNotificador, ResultadoEnvio
```

Ver todos los tipos disponibles en `packages/contracts/src/coop_contracts/__init__.py`.

---

## Criterios de aceptación de tu entregable

Tu trabajo está completo cuando:

1. **Flujo de aporte funciona de principio a fin:** audio → transcripción → JSON → confirmación → API → PDF.
2. **Flujo de retiro funciona:** si el saldo es insuficiente, el bot muestra el error en español sin stack trace.
3. **Flujo de pago funciona:** modo cuotas y modo abono-capital.
4. **Desambiguación funciona:** si el operador dice "María" y hay dos Marías en el mock, el bot pregunta.
5. **Cancelación funciona:** responder "no" o esperar 5 minutos cancela la operación sin persistir nada.
6. **Consultas funcionan:** saldo, cuotas pendientes, caja.
7. **CI pasa:** `pytest packages/bot --cov=coop_bot --cov-fail-under=70` en GitHub Actions.
8. **El bot está desplegado** en Fly.io o Railway con webhook de Telegram activo.

---

## Qué hacer si la API real se comporta distinto al mock

1. Abre un issue en el repositorio describiendo la diferencia.
2. No adaptes el bot para un comportamiento no documentado del mock.
3. Dev A ajusta la API o el mock para que sean consistentes, y actualiza `docs/05-contrato-api.md`.

El contrato (`docs/05-contrato-api.md` + schemas de `coop-contracts`) es la fuente de verdad. Si hay discrepancia, el contrato manda.

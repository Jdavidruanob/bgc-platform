# 02 — Arquitectura

---

## C4 Nivel 1 — Diagrama de contexto

```mermaid
C4Context
    title Plataforma Cooperativa — Contexto

    Person(operador, "Operador / Tesorero", "Adulto mayor. Usa el escritorio y el bot de Telegram.")
    Person(socio, "Socio", "Solo consulta. Portal web fuera de alcance en esta fase.")

    System(plataforma, "Plataforma Cooperativa", "Gestiona aportes, retiros, créditos y pagos de la cooperativa familiar.")

    System_Ext(telegram, "Telegram", "Canal de mensajería. El operador envía notas de voz y texto.")
    System_Ext(whisper, "OpenAI Whisper API", "Transcripción de audio a texto.")
    System_Ext(openai, "OpenAI Chat API", "NLU: texto → intención estructurada JSON.")
    System_Ext(postgres, "PostgreSQL (nube)", "Fly.io o Railway. Única fuente de verdad.")

    Rel(operador, plataforma, "Registra operaciones", "Escritorio o Telegram")
    Rel(operador, telegram, "Envía notas de voz y texto")
    Rel(telegram, plataforma, "Mensajes entrantes", "Webhook HTTPS")
    Rel(plataforma, telegram, "Respuestas y PDF", "API Telegram")
    Rel(plataforma, whisper, "Audio → texto", "HTTPS")
    Rel(plataforma, openai, "Texto → JSON intención", "HTTPS")
    Rel(plataforma, postgres, "Lee y escribe", "psycopg3 / TCP")
```

---

## C4 Nivel 2 — Diagrama de contenedores

```mermaid
C4Container
    title Plataforma Cooperativa — Contenedores

    Person(operador, "Operador", "")

    Container(desktop, "App de escritorio", "Python + PySide6", "Interfaz administrativa. Importa coop-core directamente. Corre en la PC del tesorero.")
    Container(bot, "coop-bot", "Python + python-telegram-bot", "Adaptador de mensajería. Whisper, NLU, máquina de estados, generación de PDF. Corre en la nube.")
    Container(api, "coop-api", "Python + FastAPI", "HTTP API. Resolución de entidades, autenticación, idempotencia. Corre en la nube.")
    ContainerDb(postgres, "PostgreSQL", "Neon / Fly Postgres / Railway", "Única fuente de verdad. Corre en la nube.")
    ContainerDb(sqlite_local, "SQLite snapshot", "Archivo local", "Copia de solo lectura. Se refresca cada 30 min. Solo para modo offline del escritorio.")

    Container_Ext(whisper, "Whisper API", "OpenAI", "Transcripción de audio")
    Container_Ext(openai_chat, "Chat API", "OpenAI", "NLU → intención JSON")
    Container_Ext(telegram_api, "Telegram Bot API", "Telegram", "Mensajería")

    Rel(operador, desktop, "Usa", "Local")
    Rel(operador, telegram_api, "Envía audio/texto", "Telegram")

    Rel(desktop, postgres, "Lee y escribe", "psycopg3 directo (coop-core)")
    Rel(desktop, sqlite_local, "Lee (modo offline)", "sqlite3")

    Rel(telegram_api, bot, "Webhook (audio/texto)", "HTTPS POST")
    Rel(bot, whisper, "Audio → transcripción", "HTTPS")
    Rel(bot, openai_chat, "Texto → intención JSON", "HTTPS")
    Rel(bot, api, "Ejecuta operaciones / consultas", "HTTPS REST")
    Rel(bot, telegram_api, "Respuestas + PDF", "HTTPS")

    Rel(api, postgres, "Lee y escribe", "psycopg3")
```

---

## Diagrama de secuencia — Flujo completo nota de voz

```mermaid
sequenceDiagram
    actor Op as Operador
    participant TG as Telegram
    participant Bot as coop-bot
    participant W as Whisper API
    participant LLM as OpenAI Chat
    participant API as coop-api
    participant DB as PostgreSQL

    Op->>TG: 🎤 "Recibí de Pedro Gómez su aporte\ny el de María por ochenta cada uno"
    TG->>Bot: webhook: audio file_id
    Bot->>TG: getFile → descarga audio
    Bot->>W: transcribeAudio(audio_bytes)
    W-->>Bot: "Recibí de Pedro Gómez su aporte y el de María por ochenta cada uno"

    Note over Bot: Registra en log: audio_url, transcripción

    Bot->>LLM: prompt_sistema + transcripción
    LLM-->>Bot: {"intencion":"registrar_aporte","recibi_de":"Pedro Gómez","aportes":[{"nombre":"Pedro Gómez","monto":80000},{"nombre":"María","monto":80000}]}

    Note over Bot: Registra en log: intención JSON

    Bot->>API: GET /socios?q=Pedro+Gómez
    API-->>Bot: [{id:12, nombre:"Pedro Gómez", score:1.0}]

    Bot->>API: GET /socios?q=María
    API-->>Bot: [{id:7, nombre:"María López", score:0.85}, {id:23, nombre:"María Ruiz", score:0.80}]

    Bot->>TG: "¿Cuál María? (1) María López  (2) María Ruiz"
    Op->>TG: "1"

    Bot->>API: GET /socios/12 (saldo actual)
    Bot->>API: GET /socios/7 (saldo actual)

    Bot->>TG: 📋 Resumen:\nAporte Pedro Gómez: $80.000 (saldo: $320.000 → $400.000)\nAporte María López: $80.000 (saldo: $150.000 → $230.000)\n¿Confirmar? (sí/no)

    Op->>TG: "sí"

    Bot->>API: POST /operaciones/aportes\n  Idempotency-Key: uuid-xyz\n  {recibi_de_id:12, aportes:[...]}
    API->>DB: BEGIN; INSERT recibo; UPDATE socios; COMMIT
    DB-->>API: recibo_id: 47
    API-->>Bot: {recibo_id:47, aportes_registrados:[...]}

    Note over Bot: Registra en log: operacion_id=47

    Bot->>Bot: generar PDF recibo #47
    Bot->>TG: ✅ Recibo #47 registrado\n📄 [PDF adjunto]
    TG->>Op: mensaje + PDF
```

---

## Diagrama de despliegue

```mermaid
graph TB
    subgraph PC_Tesorero["PC del Tesorero (Windows/Mac)"]
        Desktop["coop-desktop\nPySide6 app\n(coop-core incluido)"]
        SQLiteSnap["SQLite snapshot\n(solo lectura)"]
    end

    subgraph Nube["Nube (estimado: ~USD 12/mes)"]
        subgraph Fly["Fly.io o Railway"]
            BotContainer["coop-bot\n256 MB RAM\n~USD 3/mes"]
            APIContainer["coop-api\n256 MB RAM\n~USD 3/mes"]
        end
        subgraph DB["Base de datos"]
            PG["PostgreSQL\nNeon free tier o\nFly Postgres\n~USD 0–6/mes"]
        end
    end

    subgraph Externos["Servicios externos"]
        TelegramSvc["Telegram Bot API\nGratuito"]
        WhisperSvc["OpenAI Whisper\n~USD 0.006/min\n~USD 0.5/mes @ 200 msg"]
        LLMSvc["OpenAI GPT-4o-mini\n~USD 0.15/1M tokens\n~USD 1/mes @ 200 msg"]
    end

    Desktop -- "psycopg3 directo" --> PG
    Desktop -- "offline read" --> SQLiteSnap
    BotContainer -- "HTTPS REST" --> APIContainer
    APIContainer -- "psycopg3" --> PG
    BotContainer -- "HTTPS" --> WhisperSvc
    BotContainer -- "HTTPS" --> LLMSvc
    BotContainer -- "HTTPS webhook" --> TelegramSvc
```

**Costo estimado total: USD 7–12/mes** (variable según proveedor de Postgres).

---

## Tabla de límites de confianza

| Frontera | Datos que cruzan | Dirección | Protección |
|----------|-----------------|-----------|------------|
| Operador → Telegram | Audio de voz, texto libre | Saliente del operador | Cifrado de Telegram (E2E opcional) |
| Telegram → coop-bot | audio file_id, texto, chat_id | Entrante al bot | Token del bot en variable de entorno; webhook verificado por Telegram |
| coop-bot → Whisper API | Bytes de audio (puede contener nombres de socios) | Saliente | HTTPS + API key en var de entorno; datos no almacenados por OpenAI (modo transient) |
| coop-bot → OpenAI Chat | Texto transcrito, contexto mínimo del sistema | Saliente | HTTPS + API key; el prompt de sistema no incluye datos de socios más allá de lo transcrito |
| coop-bot → coop-api | JSON de intención + IDs resueltos de socios | Saliente del bot | HTTPS + Bearer token estático; solo desde IP del servidor del bot (firewall si lo permite el proveedor) |
| coop-api → PostgreSQL | Todos los datos financieros | Bidireccional | TLS en tránsito; credenciales en var de entorno; la DB no es accesible públicamente |
| coop-desktop → PostgreSQL | Todos los datos financieros | Bidireccional | TLS en tránsito; credenciales en var de entorno del operador |
| coop-api → coop-bot | Resultados de operaciones, datos de socios para confirmación | Respuesta HTTP | HTTPS |
| coop-bot → Telegram | Mensajes de texto, PDF de comprobante | Saliente | Cifrado de Telegram |

**Dato más sensible en tránsito:** Montos y nombres de socios reales.
**Dato nunca en tránsito hacia Dev B:** Credenciales de Postgres, código de `coop-core`, datos históricos de la DB.

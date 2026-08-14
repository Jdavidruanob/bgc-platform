# ADR-011 — Asistente de autoconsulta para socios por WhatsApp

**Estado:** Decidido
**Fecha:** 2026-08-14
**Actualiza parcialmente:** ADR-010 (que declaraba WhatsApp como canal exclusivamente de salida)

---

## Contexto

Con ADR-010, WhatsApp es un canal solo de salida: la plataforma le manda recibos y recordatorios de mora al socio, pero si el socio responde, nadie lo escucha ("se ignora o se responde con mensaje fijo"). Cualquier duda simple del socio ("¿cuánto tengo de aportes?", "¿cuándo pago?") termina en una llamada o un mensaje directo al tesorero.

Se decide abrir el canal de entrada para un caso de uso acotado: que el socio se autoconsulte, con un menú de botones fijo, sin inteligencia artificial, y con una regla dura — **cada socio solo puede ver su propia información**.

## Decisión

### 1. El webhook vive en la API, no en el bot

El bot (`packages/bot`) es un worker de long-polling sin puerto HTTP expuesto (`Dockerfile.bot`), sin `tornado` en el lockfile, y con el healthcheck de Railway retirado a propósito porque no escucha HTTP. La API en cambio ya es un servicio HTTPS público (`Dockerfile`, uvicorn), ya tiene acceso directo a Postgres, y ya tiene LibreOffice instalado para generar las liquidaciones en PDF. No se crea ningún servicio nuevo en Railway.

Nuevo router público `packages/api/src/coop_api/routers/webhook_whatsapp.py`, montado en `main.py`. Junto con `/health`, es el único endpoint sin `AuthDep` — la autenticación la da la firma HMAC de Meta (`X-Hub-Signature-256`, verificada con `WHATSAPP_APP_SECRET`), no el bearer token interno.

### 2. Sin sesión ni tabla de estado: el contexto viaja en el `id` del botón

Meta devuelve intacto el `id` que el asistente puso en cada botón (`interactive.button_reply.id` / `list_reply.id`). Ese id (`menu:aportes`, `liq:si`, `liq:letra:42`, `liq:todos`, …) es todo el contexto que necesita el siguiente turno — no hay tabla de sesiones, TTL, ni job de limpieza, y el flujo sobrevive redeploys (a diferencia del diálogo de Telegram, cuyo estado vive en `context.chat_data`, en memoria).

**Guarda de privacidad central:** el id es entrada del usuario, no una credencial. `liq:letra:<n>` siempre se revalida contra los créditos activos del socio (`CreditosRepository.find_active_by_socio_id`) antes de mandar nada. Un id manipulado, ajeno, o de un crédito ya saldado se trata exactamente igual que un id desconocido — nunca se confirma ni se niega que la letra exista.

### 3. Sin plantillas de Meta que aprobar

Como el socio siempre escribe primero, se abre la ventana de servicio al cliente de 24 horas: se puede responder con texto libre, mensajes interactivos y documentos sin plantilla aprobada — a diferencia de los recibos y recordatorios de mora (ADR-010), que si la necesitan por ser mensajes proactivos.

### 4. Cero LLM

Todo el flujo es un `match` sobre el `id` del botón (`packages/api/src/coop_api/asistente/flujo.py`). Whisper y GPT no se tocan; el bot de Telegram y su NLU no cambian. Una nota de voz, imagen, o cualquier tipo de mensaje que no sea texto o botón recibe una respuesta fija.

### 5. Excepción puntual y acotada a ADR-009 (handlers síncronos)

ADR-009 fija handlers síncronos en la API. El `POST /webhooks/whatsapp` es la única excepción: necesita el cuerpo crudo del request para verificar la firma HMAC antes de tocarlo, y eso solo se puede leer con `await request.body()`. El resto del procesamiento (las 3 consultas de solo lectura) sigue siendo síncrono dentro del mismo handler — dado el volumen esperado (~54 socios consultando ocasionalmente), no se justifica un rediseño mayor de `deps.py` para mover todo el procesamiento a un `BackgroundTask` separado.

Solo la generación de la liquidación en PDF (la parte lenta, vía LibreOffice) se delega a una `BackgroundTasks` de FastAPI, para responderle rápido al socio ("dame un momento") y no bloquear el webhook. Los datos (`DatosLiquidacion`) se arman de forma síncrona dentro del request — la conexión a la base de datos se cierra apenas termina el request, así que la tarea de fondo nunca la usa, solo trabaja con los datos ya armados.

### 6. Cliente de WhatsApp propio para el asistente, no el del bot

El bot ya tiene `CloudApiNotificador` (`packages/bot/src/coop_bot/notificaciones/notificadores.py`), pero modela avisos "dispara y olvida" con plantilla y fallback a wa.me — no mensajes interactivos (botones, listas), y el asistente nunca necesita ese fallback (si Meta falla, el socio simplemente vuelve a escribir). Además, `coop-bot` no es una dependencia de `coop-api` ni su código se copia a la imagen Docker de la API. Se acepta la duplicación de la subida de media (~40 líneas); si crece, se puede extraer a `coop_contracts`.

## Guarda de rollout: lista blanca

`WHATSAPP_ASISTENTE_NUMEROS` (env var de la API) es una lista blanca de números autorizados, separada por comas. **Vacía o ausente = el asistente no le responde a nadie** (default seguro). Se activa progresivamente: primero solo el número del administrador y 2-3 socios de confianza, y cuando esté validado en producción, se cambia a `*` para abrir a los ~54 socios.

## Alcance

**Dentro de alcance:** 3 consultas de solo lectura — saldo de aportes, créditos activos (con envío opcional de la liquidación al día de hoy en PDF), y próximos pagos (incluye cuotas ya en mora).

**Fuera de alcance:**
- Cualquier operación que escriba en la base (registrar pagos, aportes, créditos) — el asistente es estrictamente de solo lectura.
- El flujo de Telegram del tesorero, que no cambia.
- Persistencia de conversaciones — el diseño es deliberadamente sin estado.
- Historial de créditos ya saldados (`find_active_by_socio_id` solo trae los activos).

## Deuda conocida

`liquidaciones.mora_exenta` existe en el schema de Postgres pero ningún código la lee todavía (ni el endpoint `GET /creditos/{letra}/cuotas-pendientes` existente, ni este asistente). Si el tesorero exime una cuota de mora, tanto ese endpoint como el asistente seguirán mostrándole al socio una mora que no debería cobrarse. No se corrige en este ADR porque afecta un endpoint ya existente y merece su propia decisión — queda registrado aquí para no perderlo de vista.

## Consecuencias

**Ganamos:** los socios se autoatienden para las 3 consultas más comunes sin depender del tesorero, sin tabla de sesiones que mantener, sin tocar el flujo de Telegram, y sin esperar aprobación de plantillas de Meta.

**Perdemos:** un socio sin `whatsapp_e164`/`celular` reconocible no puede usar el asistente (mismo límite que ya existía para notificaciones salientes, ADR-010). El identificador de botón (`liq:letra:<n>`) queda tapable indefinidamente en el historial del chat del socio; si la gramática de ids cambia en el futuro, un id viejo simplemente cae al menú principal en vez de fallar.

# 01 — Requisitos

> Convención de prioridad MoSCoW: **M** = Must, **S** = Should, **C** = Could, **W** = Won't (esta fase).

---

## Los dos flujos del bot

### Flujo 1 — Consulta
El operador pregunta. El bot responde con datos actuales. No hay confirmación, no se genera documento, no se modifica nada.

```
Operador (Telegram) → Bot → API → Respuesta en texto (Telegram)
```

### Flujo 2 — Operación
El operador da una instrucción. El bot entiende, muestra un resumen y pide confirmación. Tras el "sí", ejecuta la operación, genera el documento correspondiente, lo guarda en la DB y lo envía:
- **Al operador** por Telegram (siempre).
- **Al/los socios involucrados** por WhatsApp (si tienen número registrado).

```
Operador (Telegram)
  → Bot (NLU + confirmación)
  → API (operación + generación de documento)
  → PDF del documento
  → Telegram al operador  ✅ siempre
  → WhatsApp al/los socios involucrados  ✅ si tienen número
```

**Documentos generados por tipo de operación:**

| Operación | Documento | Se envía al socio |
|-----------|-----------|-------------------|
| Aporte / Retiro / Pago cuota / Combinado / Abono capital | Recibo | Sí (todos los socios del recibo) |
| Nuevo crédito | Tabla de liquidación (amortización) | Sí (todos los socios del crédito) |

---

## Requisitos Funcionales

### Consultas (Flujo 1)

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-01 | M | El bot consulta información de un socio: saldo, nombre completo, número de WhatsApp registrado | Dado "¿Cuánto tiene Pedro Gómez?", el bot responde con saldo actual en texto sin pedir confirmación |
| RF-02 | M | El bot entrega la liquidación actual de un crédito (tabla de cuotas pendientes) | Dado "¿Cuánto debe Carlos de la letra 450?", el bot responde con cuotas pendientes, montos y próxima fecha de vencimiento |
| RF-03 | S | El bot consulta el saldo de caja | "¿Cuánto hay en caja?" → respuesta inmediata |

---

### Operaciones (Flujo 2)

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-10 | M | El bot recibe notas de voz y las transcribe a texto | Audio de hasta 120 s en español → transcripción disponible en ≤ 8 s |
| RF-11 | M | El bot interpreta el texto y extrae una intención estructurada (JSON) | JSON válido conforme a schemas de `coop-contracts` para ≥ 95 % de mensajes del corpus de prueba |
| RF-12 | M | Antes de ejecutar cualquier operación, el bot presenta un resumen legible y espera confirmación explícita | El operador debe responder "sí" / "confirmar" o variante; cualquier otra respuesta o silencio > 5 min cancela la operación |
| RF-13 | M | El bot registra **aportes** de uno o varios socios | Tras confirmación, ejecuta `AporteService.register`, genera recibo PDF, envía por Telegram al operador y por WhatsApp a cada socio del recibo que tenga número registrado |
| RF-14 | M | El bot registra **retiros** | Ídem con `RetiroService.register` |
| RF-15 | M | El bot registra **pagos de cuotas** (modo manual y modo abono-capital) | Ídem con `PagoService.register` |
| RF-16 | M | El bot registra **operaciones combinadas** (aporte + pago en un recibo) | Ídem con `CombinadoService.register` |
| RF-17 | M | El bot **crea nuevos créditos** | Tras confirmación, ejecuta `CreditoService.create`, genera la tabla de amortización en PDF, envía por Telegram al operador y por WhatsApp a cada socio del crédito |
| RF-18 | M | El bot registra **abonos a capital** | Incluido en el modo abono-cascada de `PagoService` |
| RF-19 | M | El bot envía el comprobante (recibo o liquidación) **a todos los socios involucrados** en la operación por WhatsApp | Si hay 2 socios en un recibo, ambos reciben el PDF. Si un socio no tiene número registrado, se registra en log y se continúa sin error |
| RF-20 | M | Si WhatsApp falla, la operación continúa y la notificación queda en cola para reintento o fallback | El fallo de WhatsApp nunca bloquea ni revierte la operación financiera |
| RF-21 | M | El bot resuelve nombres a IDs de socios con desambiguación si hay más de un candidato | Ver política de resolución en `docs/04-contrato-intenciones.md` |
| RF-22 | M | El bot maneja la cancelación en cualquier punto del flujo | El operador puede escribir "cancelar" o "no" y el bot aborta sin ejecutar nada |
| RF-23 | M | El bot responde también a mensajes de texto (no solo audio) | Mismo flujo NLU → confirmación → commit |
| RF-24 | M | Los errores de validación del backend se muestran al operador en español | Si la API retorna 422 con mensaje de negocio, el bot lo muestra tal cual |

---

### Notificaciones proactivas

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-30 | S | El sistema envía recordatorio a socios con cuota que vence en los próximos 5 días | Job diario a las 8 am; cada socio recibe máximo 1 recordatorio previo por cuota |
| RF-31 | S | El sistema envía recordatorio a socios con cuota vencida | Recordatorio al día siguiente del vencimiento y cada 7 días mientras siga sin pagar |
| RF-32 | S | El fallback `wa.me` genera un enlace que el operador puede abrir y enviar manualmente | Si Cloud API falla, el bot envía al operador (Telegram) un enlace `wa.me` con el texto pre-redactado |

---

### API (`coop-api`)

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-40 | M | La API expone todos los endpoints de operación del dominio | Mapean 1:1 a servicios de `coop-core`; retornan 201 en éxito |
| RF-41 | M | La API expone endpoints de consulta | Retornan 200 con JSON del estado actual |
| RF-42 | M | Todos los endpoints de operación validan clave de idempotencia | Mismo `Idempotency-Key` → misma respuesta, sin re-ejecutar |
| RF-43 | M | La API propaga errores de negocio (`ValueError`) como 422 en español | `detail` contiene el mensaje original del servicio |
| RF-44 | M | La API tiene endpoint de búsqueda fuzzy de socios por nombre | `GET /socios?q=juan` retorna candidatos con score |
| RF-45 | M | La API gestiona la cola de notificaciones WhatsApp pendientes | Tabla `notificaciones_whatsapp`; endpoint `GET /notificaciones/pendientes` y `PATCH /notificaciones/{id}` |
| RF-46 | M | La API tiene un job programado para generar recordatorios de cuotas | Cron diario; usa `notif_prev_enviada` / `notif_venc_enviada` para idempotencia |

---

### App de escritorio

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-50 | M | La app sigue funcionando igual tras la migración a Postgres | Todas las operaciones producen el mismo resultado |
| RF-51 | M | La app se conecta a Postgres en la nube | Con internet, todas las operaciones persisten en Postgres |
| RF-52 | M | La app muestra modo lectura (snapshot SQLite) cuando no hay internet | Escritura deshabilitada en modo offline |
| RF-53 | S | El snapshot se refresca automáticamente cada 30 minutos | Timestamp del último refresco visible en la UI |

---

### `coop-core`

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-60 | M | `coop-core` es instalable sin dependencias de PySide6 | `pip install coop-core` en entorno limpio no instala Qt |
| RF-61 | M | Los repositorios son compatibles con Postgres (psycopg3) | Sin `DATE('now')` ni `sqlite_sequence` |
| RF-62 | M | `get_hoy()` tiene override para tests | `set_fecha_simulada(date(...))` funciona en todos los tests |

---

## Requisitos No Funcionales

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RNF-01 | M | **Integridad financiera:** ninguna operación se ejecuta de forma parcial | Rollback explícito en todos los servicios ante cualquier fallo |
| RNF-02 | M | **Idempotencia:** reenviar el mismo request no duplica el movimiento | Mismo `Idempotency-Key` → mismo resultado, operación no re-ejecutada |
| RNF-03 | M | **Dinero en enteros:** ningún monto se calcula o almacena como `float` | mypy strict + tests verifican que todos los campos de monto son `int` |
| RNF-04 | M | **Notificaciones no bloqueantes:** si WhatsApp falla, la operación financiera ya fue confirmada y persiste | El fallo queda en `notificaciones_whatsapp.estado = 'fallido'`; no hay rollback de la operación |
| RNF-05 | M | **Latencia del bot:** audio → resumen de confirmación en ≤ 15 s | Medido en tests con audio de 30 s en conexión de 10 Mbps |
| RNF-06 | M | **Trazabilidad:** cada operación por voz tiene registro inmutable de audio, transcripción, JSON de intención e ID de operación resultante | Registro en `audit_log` antes de que se confirme la operación |
| RNF-07 | M | **Autenticación del bot:** solo el operador autorizado puede enviar comandos | Bot verifica `chat_id` en lista blanca antes de procesar cualquier mensaje |
| RNF-08 | M | **Consentimiento WhatsApp:** solo se envían mensajes a socios con `optin_whatsapp_fecha` registrada | El job de notificaciones filtra socios sin consentimiento antes de encolar |
| RNF-09 | S | **Cobertura de tests:** `core` ≥ 90 %, `api` ≥ 75 %, `bot` ≥ 70 % | `pytest --cov` en CI; el merge se bloquea si no se alcanzan |
| RNF-10 | S | **Tipado estático:** todo el código pasa `mypy --strict` | CI corre mypy y falla si hay errores |
| RNF-11 | S | **Costo de infraestructura ≤ USD 20/mes** | Documentado en `docs/02-arquitectura.md` |

---

## Límites del sistema — qué NO hace

- El bot **no envía mensajes a socios sin consentimiento previo** (`optin_whatsapp_fecha` registrada).
- El bot **no tiene diálogo con los socios** — WhatsApp es canal de salida únicamente.
- El sistema **no permite escritura offline** bajo ninguna circunstancia.
- El sistema **no tiene portal web de socios** en esta fase.
- La IA **no calcula montos, intereses, cuotas ni saldos** — solo interpreta lenguaje natural.
- El sistema **no soporta múltiples operadores concurrentes** en esta fase.
- Una notificación WhatsApp fallida **no revierte ni cancela la operación financiera** asociada.

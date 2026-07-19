# 01 — Requisitos

> Convención de prioridad MoSCoW: **M** = Must, **S** = Should, **C** = Could, **W** = Won't (esta fase).

---

## Requisitos Funcionales

### Bot de mensajería (prioridad #1)

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-01 | M | El bot recibe mensajes de voz y los transcribe a texto | Dado un audio de hasta 120 s en español, la transcripción está disponible en ≤ 8 s con tasa de error de palabras (WER) aceptable para nombres y montos en pesos colombianos |
| RF-02 | M | El bot interpreta el texto transcrito y extrae una intención estructurada (JSON) | El LLM produce un objeto JSON válido conforme al schema de `coop-contracts` para ≥ 95 % de los mensajes del corpus de prueba |
| RF-03 | M | Antes de ejecutar cualquier operación que mueva dinero, el bot presenta un resumen legible y espera confirmación explícita | El usuario debe responder "sí" / "confirmar" (o variante reconocida) para que la operación se ejecute; cualquier otra respuesta la cancela |
| RF-04 | M | El bot registra aportes de uno o varios socios en un solo mensaje | Dado "recibí de Pedro Gómez el aporte de él y de María López por 80.000 cada uno", el bot extrae dos aportes, muestra el resumen y ejecuta `AporteService.register` tras confirmación |
| RF-05 | M | El bot registra retiros | Dado "Juan Ruiz retiró 200.000", el bot ejecuta `RetiroService.register` tras confirmación |
| RF-06 | M | El bot registra pagos de cuotas de crédito | Soporta modo cuotas (n cuotas de una letra) y modo abono-capital |
| RF-07 | M | El bot registra operaciones combinadas (aporte + pago en un solo mensaje) | El bot detecta ambas intenciones, las agrupa en una sola operación y llama `CombinadoService.register` |
| RF-08 | M | El bot entrega un PDF de comprobante tras cada operación exitosa | El PDF contiene la misma información del recibo Excel existente: ID de recibo, fecha, socio, montos, saldo |
| RF-09 | M | El bot resuelve nombres de socios a IDs internos | Dado "Juan", el bot busca en el padrón; si hay un único match tolerable, usa ese ID; si hay ambigüedad, pregunta al operador |
| RF-10 | M | El bot maneja errores de validación del backend con mensajes en español | Si `coop-api` retorna 422 con mensaje de negocio, el bot lo muestra tal cual al operador sin traducción técnica |
| RF-11 | M | El bot soporta cancelar una operación en cualquier punto del flujo de confirmación | El operador puede escribir "cancelar" o "no" y el bot aborta sin ejecutar nada |
| RF-12 | S | El bot responde también a mensajes de texto (no solo audio) | Un mensaje de texto sigue el mismo flujo NLU → confirmación → commit |
| RF-13 | S | El bot permite consultar el saldo de un socio | "¿Cuánto tiene Pedro Gómez?" → el bot responde con saldo actual sin pedir confirmación |
| RF-14 | S | El bot permite consultar cuotas pendientes de un crédito | "¿Cuánto debe Carlos Ruiz de la letra 450?" → cuotas pendientes y próxima fecha de vencimiento |
| RF-15 | S | El bot permite consultar el saldo de caja | "¿Cuánto hay en caja?" → respuesta inmediata, sin confirmación |
| RF-16 | C | El bot notifica próximos vencimientos de cuotas en forma proactiva | Envío diario/semanal de lista de cuotas que vencen en los próximos 7 días |
| RF-17 | W | El bot puede crear nuevos socios | Fuera de alcance en esta fase |
| RF-18 | W | El bot puede crear nuevos créditos vía voz | Complejidad alta (múltiples parámetros). Fuera de alcance en esta fase |

---

### API (`coop-api`)

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-20 | M | La API expone todos los endpoints de operación del dominio (aportes, retiros, pagos, combinados) | Cada endpoint mapea 1:1 a un método de servicio de `coop-core`; retorna 201 en éxito |
| RF-21 | M | La API expone endpoints de consulta (socios, saldos, créditos, cuotas pendientes) | Retornan 200 con JSON; los datos reflejan el estado actual de la DB |
| RF-22 | M | Todos los endpoints de operación aceptan y validan una clave de idempotencia | Dado el mismo `Idempotency-Key`, el segundo request retorna la misma respuesta que el primero sin re-ejecutar la operación |
| RF-23 | M | La API propaga los mensajes de error de negocio (`ValueError`) como respuestas 422 en español | El campo `detail` del error contiene el mensaje original del servicio, listo para mostrar al operador |
| RF-24 | M | La API tiene un endpoint de resolución de entidades (búsqueda fuzzy de socios por nombre) | `GET /socios?q=juan` retorna candidatos ordenados por score; el bot elige o pide desambiguación |
| RF-25 | M | La API requiere autenticación con token estático en esta fase | Requests sin `Authorization: Bearer <token>` retornan 401 |
| RF-26 | S | La API registra en log estructurado cada operación de escritura con: timestamp, operador, endpoint, payload (sin datos sensibles), resultado | Los logs son accesibles en la plataforma de despliegue (Fly.io o Railway) |

---

### App de escritorio

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-30 | M | La app de escritorio sigue funcionando exactamente igual que antes de la migración | Todas las operaciones existentes producen el mismo resultado antes y después de migrar a Postgres |
| RF-31 | M | La app se conecta a la base de datos Postgres en la nube | Al abrir la app con internet, se conecta a Postgres; todas las operaciones persisten en la nube |
| RF-32 | M | La app muestra un modo lectura (snapshot SQLite local) cuando no hay internet | En modo offline, las operaciones de escritura están deshabilitadas; solo se pueden consultar datos del último snapshot |
| RF-33 | S | El snapshot local se refresca automáticamente cada 30 minutos cuando hay conexión | El timestamp del último refresco es visible en la UI |

---

### `coop-core`

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RF-40 | M | `coop-core` es instalable como paquete Python sin dependencias de PySide6 | `pip install coop-core` en un entorno limpio no instala Qt |
| RF-41 | M | Los servicios de `coop-core` son compatibles con Postgres (psycopg3) | Los repositorios usan SQL estándar; no hay `DATE('now')` ni `sqlite_sequence` |
| RF-42 | M | La función `get_hoy()` tiene un mecanismo de override para tests | `set_fecha_simulada(date(...))` funciona en todos los tests sin monkeypatching |

---

## Requisitos No Funcionales

| ID | Prioridad | Descripción | Criterio de aceptación |
|----|-----------|-------------|------------------------|
| RNF-01 | M | **Integridad financiera:** ninguna operación que mueva dinero puede ejecutarse de forma parcial | Si cualquier paso de la transacción falla, la DB vuelve al estado anterior (rollback explícito en todos los servicios) |
| RNF-02 | M | **Idempotencia:** reenviar el mismo request de operación no duplica el movimiento | El segundo request con la misma `Idempotency-Key` retorna 200 con el resultado original sin ejecutar la operación de nuevo |
| RNF-03 | M | **Dinero en enteros:** ningún monto se calcula o almacena como `float` | mypy en modo strict + tests de propiedad verifican que todos los campos de monto son `int` |
| RNF-04 | M | **Disponibilidad básica:** la API está disponible ≥ 99 % del tiempo durante horario de operación (lun–sáb 8 am–6 pm) | Medido con health check cada 5 minutos desde Fly.io/Railway; se acepta la indisponibilidad por mantenimiento fuera de horario |
| RNF-05 | M | **Latencia del bot:** el tiempo entre enviar el audio y recibir el resumen para confirmación es ≤ 15 s en condiciones normales de red | Medido en tests de integración con audio de 30 s en conexión de 10 Mbps |
| RNF-06 | M | **Trazabilidad de operaciones por voz:** cada operación originada en el bot tiene un registro de auditoría inmutable con: audio original (URL), transcripción, JSON de intención, ID de operación resultante | Verificable en los logs de la API; el registro existe antes de que se confirme la operación |
| RNF-07 | M | **Autenticación del bot:** solo el operador autorizado puede enviar comandos de escritura | El bot valida que el chat_id de Telegram del operador esté en la lista blanca antes de procesar cualquier mensaje |
| RNF-08 | S | **Cobertura de tests:** `coop-core` ≥ 90 %; `coop-api` ≥ 80 %; `coop-bot` ≥ 70 % | `pytest --cov` reporta estos valores; el CI bloquea el merge si no se alcanzan |
| RNF-09 | S | **Tipado estático:** todo el código pasa `mypy --strict` | El CI corre mypy y falla si hay errores de tipo |
| RNF-10 | S | **Escalabilidad vertical suficiente:** la API maneja 20 requests concurrentes sin degradación perceptible | Dado que el volumen real es ~200 msg/mes, un servidor de 512 MB RAM es suficiente; no se requiere escalado horizontal |
| RNF-11 | S | **Costo de infraestructura ≤ USD 20/mes** | Documentado en el diagrama de despliegue; revisable cada trimestre |
| RNF-12 | C | **Tiempo de recuperación ante falla del servidor:** ≤ 4 horas | Respaldado por los backups automáticos del proveedor de Postgres |

---

## Límites del sistema — qué NO hace

- El bot **no crea socios nuevos** (RF-17).
- El bot **no crea créditos nuevos** vía voz en esta fase (RF-18).
- El sistema **no permite escritura offline** bajo ninguna circunstancia.
- El sistema **no tiene portal web de socios** en esta fase (decisión ya tomada).
- La IA (LLM/Whisper) **no calcula montos, intereses, cuotas ni saldos**. Solo interpreta lenguaje natural.
- El bot **no envía comprobantes a los socios**; solo al operador.
- El sistema **no soporta múltiples operadores concurrentes** en esta fase.
- El sistema **no tiene recuperación de contraseñas ni gestión de usuarios**; el acceso se configura manualmente.

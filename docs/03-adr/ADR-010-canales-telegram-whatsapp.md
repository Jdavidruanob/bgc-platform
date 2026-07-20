# ADR-010 — Arquitectura de dos canales: Telegram (entrada) + WhatsApp (salida)

**Estado:** Decidido  
**Fecha:** 2026-07-20  
**Reemplaza:** ADR-004 (que planteaba un solo canal con adaptador)

---

## Contexto

El sistema tiene dos tipos de comunicación con propósitos completamente distintos:

1. **El operador (tesorero) da órdenes al bot** — conversacional, con estado, con IA, con confirmación.
2. **El sistema notifica a los socios** — transaccional, sin diálogo, sin IA, push puro.

Unificarlos en un solo canal introduciría complejidad innecesaria y acoplaría la lógica conversacional con la de notificaciones.

## Decisión

**Dos canales separados, con propósitos y direcciones distintas. No se unifican.**

### Canal de entrada — Telegram

Uso exclusivo del tesorero (un solo usuario). Aquí vive todo el flujo conversacional:
- Recibe notas de voz y texto.
- Mantiene estado del diálogo (máquina de estados).
- Corre Whisper + LLM para NLU.
- Pide confirmación explícita antes de cada commit.
- Responde con texto y envía el comprobante en PDF.

### Canal de salida — WhatsApp Cloud API

Canal de notificación a los socios. Sin diálogo, sin estado, sin IA:
- Envía recibos en PDF al/los socios involucrados en cada operación.
- Envía recordatorios de cuota próxima/vencida (job programado).
- Si un socio responde, se ignora o se responde con mensaje fijo ("Consulte al tesorero").

**Restricciones operativas aceptadas:**
- Cuenta sin verificar por Meta: límite de 250 destinatarios únicos por 24 horas. Con ~50 socios, sobra.
- Número dedicado via eSIM, no registrado en la app normal de WhatsApp.
- Los mensajes proactivos requieren plantillas de utilidad aprobadas por Meta.

## Interfaz `Notificador` y sus implementaciones

```python
# packages/contracts/src/coop_contracts/notificador.py

from pathlib import Path
from typing import Protocol
from dataclasses import dataclass

@dataclass
class ResultadoEnvio:
    exitoso: bool
    mensaje_id: str | None = None
    error: str | None = None

class Notificador(Protocol):
    def enviar(
        self,
        socio_id: int,
        plantilla: str,
        parametros: dict,
        adjunto: Path | None = None,
    ) -> ResultadoEnvio: ...
```

**Tres implementaciones** (todas en `packages/bot/`, responsabilidad de Dev B):

| Implementación | Cuándo se usa |
|---------------|---------------|
| `CloudApiNotificador` | Producción con Meta Cloud API configurada |
| `WaMeLinkNotificador` | Fallback: genera enlaces `wa.me` que el tesorero abre y envía desde su teléfono. Sin adjuntos, solo texto. Funciona sin cuenta de Meta. |
| `MockNotificador` | Desarrollo y tests. No envía nada, registra en log. |

**El fallback `WaMeLinkNotificador` no es opcional.** Es el plan de contingencia si Meta restringe la cuenta y también permite operar desde el día uno mientras se configura Cloud API.

## Plantillas WhatsApp necesarias

Deben estar redactadas en tono transaccional para evitar clasificación como marketing por Meta:

| Nombre plantilla | Cuándo se envía | Adjunto |
|-----------------|-----------------|---------|
| `recibo_operacion` | Tras registrar aporte, retiro, pago o combinado | PDF del recibo |
| `liquidacion_credito` | Tras crear un crédito nuevo | PDF de la tabla de amortización |
| `recordatorio_cuota_proxima` | 5 días antes del vencimiento de una cuota | No |
| `recordatorio_cuota_vencida` | Al día siguiente del vencimiento (y cada 7 días) | No |

## Cambios al modelo de datos

```sql
-- Agregar a tabla socios:
ALTER TABLE socios ADD COLUMN whatsapp_e164 TEXT;       -- ej: "+573001234567"
ALTER TABLE socios ADD COLUMN optin_whatsapp_fecha DATE; -- fecha de consentimiento (exigido por Meta)

-- Nueva tabla de registro de envíos:
CREATE TABLE notificaciones_whatsapp (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    socio_id        INTEGER REFERENCES socios(id),
    plantilla       TEXT NOT NULL,
    parametros      JSONB NOT NULL,
    adjunto_path    TEXT,
    estado          TEXT NOT NULL DEFAULT 'pendiente', -- pendiente | enviado | fallido | fallback_walink
    mensaje_id_meta TEXT,   -- ID retornado por Meta Cloud API
    error           TEXT,
    intentos        INT NOT NULL DEFAULT 0
);
```

## Flujo de notificación post-operación

```
Bot (Telegram)
  │
  │ POST /operaciones/aportes → response con recibo_id + socios_a_notificar
  │
  ▼
API guarda en notificaciones_whatsapp (estado='pendiente') para cada socio
  │
  ▼
Bot consulta GET /notificaciones/pendientes
  │
  ├── Para cada notificación pendiente:
  │     Bot genera PDF (si aplica)
  │     Bot llama CloudApiNotificador.enviar(...)
  │     Si falla → WaMeLinkNotificador.enviar(...) o registra error
  │     Bot llama PATCH /notificaciones/{id} con estado resultante
```

**Las notificaciones NUNCA son bloqueantes.** Si fallan, la operación principal ya fue confirmada y persistida. El fallo queda en `notificaciones_whatsapp.estado = 'fallido'` para reintento manual.

## Flujo de recordatorios (job programado)

```
Job en api/ (cron diario, 8 am)
  │
  │ Consulta liquidaciones con fecha_vencimiento en los próximos 5 días
  │ o ya vencidas (y notif_prev_enviada/notif_venc_enviada = false)
  │
  ▼
Inserta filas en notificaciones_whatsapp (estado='pendiente')
  │
  ▼
Bot procesa la cola (igual que post-operación)
```

El job usa `notif_prev_enviada` y `notif_venc_enviada` de la tabla `liquidaciones` (ya existentes en el schema actual) para garantizar idempotencia: aunque el job corra dos veces el mismo día, no duplica el envío.

## División de responsabilidades

| Qué | Quién |
|-----|-------|
| Decidir quién se notifica y cuándo | Dev A (`core/` + job en `api/`) |
| Implementar `Notificador` (CloudAPI, WaMe, Mock) | Dev B (`bot/`) |
| Definir la interfaz `Notificador` y las plantillas | Dev A (`contracts/`) |
| Enviar la notificación efectivamente | Dev B (`bot/`) |

## Alternativas descartadas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Un solo canal (WhatsApp para todo) | El tesorero necesita diálogo conversacional. WhatsApp con el modelo de plantillas aprobadas no permite flujos de confirmación libre. |
| Un solo canal (Telegram para todo) | Los socios no tienen Telegram. WhatsApp es el canal de facto en Colombia para comunicaciones de este tipo. |
| WhatsApp para todo con Business API verificada | El proceso de verificación de Meta requiere número empresarial y documentación legal. Ralentiza el lanzamiento. |

## Consecuencias

**Ganamos:**
- El tesorero usa el canal conversacional que permite NLU libre (Telegram).
- Los socios reciben notificaciones en el canal que ya usan (WhatsApp).
- El fallback `wa.me` permite operar desde el día uno sin depender de Meta.
- Las notificaciones nunca bloquean una operación.

**Perdemos:**
- Dos canales = dos configuraciones de deploy.
- Riesgo de que Meta restrinja la cuenta sin verificar (mitigado por fallback).
- Los socios sin `whatsapp_e164` registrado no reciben notificaciones automáticas.

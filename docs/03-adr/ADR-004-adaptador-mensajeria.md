# ADR-004 — Canal de mensajería detrás de un adaptador

**Estado:** Decidido  
**Fecha:** 2026-07-18

---

## Contexto

El bot necesita un canal de mensajería. Telegram y WhatsApp Cloud API son las opciones principales. La elección afecta el desarrollo de Dev B y el despliegue.

## Decisión

Arrancar con **Telegram**. El código del bot separa claramente el adaptador de mensajería (capa de transporte) del resto del bot (NLU, máquina de estados, lógica de confirmación). Cambiar a WhatsApp Cloud API no debe requerir tocar NLU, diálogo ni llamadas a la API.

La interfaz del adaptador expone:
```python
class MensajeEntrada:
    chat_id: str
    texto: str | None
    audio_bytes: bytes | None

class AdaptadorMensajeria(Protocol):
    async def send_text(self, chat_id: str, texto: str) -> None: ...
    async def send_document(self, chat_id: str, nombre: str, bytes_: bytes) -> None: ...
    async def set_webhook(self, url: str) -> None: ...
```

## Alternativas consideradas

| Alternativa | Por qué se descartó en esta fase |
|-------------|----------------------------------|
| WhatsApp Cloud API | Requiere número de teléfono empresarial, proceso de aprobación de Meta, y plantillas de mensajes aprobadas para notificaciones. Telegram no tiene ninguna de estas fricciones. La feature parity para este caso de uso es equivalente. |
| WhatsApp Business API (proveedor tercero: Twilio, 360dialog) | Costo adicional (~USD 0.05–0.10 por conversación) + dependencia de un intermediario. Telegram es gratuito. |
| Signal | Sin API oficial para bots. |

## Consecuencias

**Ganamos:**
- Telegram tiene API de bots madura, sin aprobaciones, gratuita, con soporte nativo para archivos (PDF) y audio.
- Desarrollo más rápido: el SDK `python-telegram-bot` está muy maduro.

**Perdemos:**
- El tesorero necesita tener Telegram instalado. Si prefiere WhatsApp, el adaptador deberá cambiarse (es el costo aceptado de esta decisión).
- El aislamiento del adaptador es un contrato a mantener; si Dev B acopla código al SDK de Telegram fuera del adaptador, el cambio futuro se complica.

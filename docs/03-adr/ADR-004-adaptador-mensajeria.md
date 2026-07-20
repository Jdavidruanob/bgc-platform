# ADR-004 — Canal de mensajería

**Estado:** Supersedido por ADR-010  
**Fecha original:** 2026-07-18

---

Este ADR fue reemplazado por **ADR-010 — Arquitectura de dos canales: Telegram (entrada) + WhatsApp (salida)**.

La decisión evolucionó de "un canal con adaptador intercambiable" a "dos canales con propósitos distintos y no intercambiables":
- **Telegram**: canal conversacional del operador (entrada, con IA y estado).
- **WhatsApp Cloud API**: canal de notificación a socios (salida, sin diálogo, transaccional).

Ver `docs/03-adr/ADR-010-canales-telegram-whatsapp.md` para la especificación completa.

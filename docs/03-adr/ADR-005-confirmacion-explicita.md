# ADR-005 — Confirmación explícita obligatoria antes de todo commit

**Estado:** Decidido  
**Fecha:** 2026-07-18

---

## Contexto

El flujo del bot interpreta lenguaje natural, que es impreciso. Una transcripción errónea o una alucinación del LLM podría resultar en registrar el monto o el socio equivocado. Operar sobre dinero real de personas reales exige una salvaguarda.

## Decisión

Ninguna operación que modifique datos financieros (aportes, retiros, pagos, créditos) se ejecuta sin que el operador vea un resumen estructurado en texto y responda explícitamente "sí", "confirmar", "ok" o variante reconocida. Cualquier otra respuesta (incluyendo silencio por timeout de 5 minutos) cancela la operación.

El resumen debe incluir, como mínimo:
- Tipo de operación
- Nombre del socio (tal como está en la DB, no como fue dicho en voz)
- Monto en pesos colombianos formateado
- Saldo resultante del socio (cuando aplique)
- Número de cuotas y letra (para pagos)

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Confirmación implícita (ejecutar directo si el LLM tiene alta confianza) | El riesgo de un monto o socio incorrecto es inaceptable para operaciones financieras reales. La "confianza" del LLM no es una garantía de corrección. |
| Confirmación solo para montos grandes (> X pesos) | Define una frontera arbitraria. El tesorero podría no notar un error en un monto "pequeño" que siga siendo real. Consistencia es más segura. |

## Consecuencias

**Ganamos:**
- El operador tiene una última línea de defensa antes de cualquier error. Si la transcripción o el NLU se equivocan, el operador lo ve antes de que sea persistido.
- Los errores se detectan antes del commit, no después (cuando revertirlos es más difícil).

**Perdemos:**
- El flujo requiere al menos 2 mensajes por operación (resumen + confirmación) en lugar de 1. Es una fricción aceptable dado el contexto.
- Si el operador confirma un resumen incorrecto (no lo leyó), el error se ejecuta igualmente. La herramienta no sustituye la atención del operador.

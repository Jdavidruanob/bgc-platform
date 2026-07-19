# ADR-009 — FastAPI con handlers síncronos (no async)

**Estado:** Propuesto  
**Fecha:** 2026-07-18

---

## Contexto

FastAPI soporta tanto handlers síncronos (`def`) como asíncronos (`async def`). psycopg3 tiene tanto una API síncrona como una asíncrona. Los servicios actuales de `coop-core` son síncronos.

## Decisión

Los handlers de `coop-api` y los repositorios de `coop-core` usan la API **síncrona** de psycopg3. FastAPI ejecuta los handlers síncronos en un thread pool, por lo que no bloquean el event loop.

## Alternativas consideradas

| Alternativa | Trade-offs |
|-------------|-----------|
| Async handlers + psycopg3 async | Mayor throughput bajo carga alta concurrente. Pero requiere reescribir todos los repositorios con `async/await` y cambiar el patrón de transacciones. A 200 requests/mes el throughput no es el cuello de botella. El esfuerzo no se justifica. |

## Consecuencias

**Ganamos:**
- Los servicios de `coop-core` siguen siendo síncronos: el escritorio (Qt no es async-friendly) y la API los pueden usar sin adaptar.
- Código más simple: sin `async/await` en la lógica de negocio.

**Perdemos:**
- Si en el futuro el volumen crece 100x y la latencia de DB se vuelve el cuello de botella, habría que migrar a async. A la escala actual (50 socios, 200 msg/mes) esto es hipotético.
- FastAPI en modo síncrono usa un thread pool con tamaño predeterminado (40 threads). Más que suficiente para este caso.

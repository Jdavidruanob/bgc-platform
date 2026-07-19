# ADR-003 — Sin escritura offline; snapshot SQLite de solo lectura

**Estado:** Decidido  
**Fecha:** 2026-07-18

---

## Contexto

El escritorio corre en la PC del tesorero. Si no hay internet, no puede conectarse a Postgres. La decisión es qué hacer en ese caso.

## Decisión

Si no hay internet, el escritorio abre un snapshot SQLite local de **solo lectura** que se refresca automáticamente cada 30 minutos cuando hay conexión. Escribir offline está prohibido por diseño: no hay botón de guardar en modo offline, no hay cola de operaciones pendientes.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Cola de operaciones offline que se sincroniza al reconectar | Introduce conflictos de escritura concurrente (ej: el bot registra un retiro mientras el escritorio offline registra el mismo aporte → saldos incoherentes). Resolver merge conflicts sobre dinero es inaceptable. |
| Bloquear completamente la app sin internet | El tesorero puede necesitar consultar saldos o historial aunque no haya internet. El snapshot de lectura resuelve esto. |
| Permitir escritura offline con "último en escribir gana" | Cualquier política de merge sobre datos financieros introduce riesgo de pérdida o duplicación de movimientos. |

## Consecuencias

**Ganamos:**
- Modelo de consistencia simple: una sola fuente de verdad, sin sincronización.
- El tesorero puede consultar saldos e historial reciente sin internet.

**Perdemos:**
- Si no hay internet durante una reunión de cobro, no se pueden registrar operaciones. El tesorero debe tener conexión para operar. Esto es una restricción real y debe comunicarse.
- El snapshot puede estar desactualizado hasta 30 minutos. Aceptable para consultas; no es información en tiempo real.

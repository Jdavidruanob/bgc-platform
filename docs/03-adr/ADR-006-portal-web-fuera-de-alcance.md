# ADR-006 — Portal web de socios fuera de alcance en esta fase

**Estado:** Decidido  
**Fecha:** 2026-07-18

---

## Contexto

Una de las motivaciones del proyecto es que los socios puedan consultar su saldo y movimientos sin llamar al tesorero. Un portal web sería el canal natural.

## Decisión

El portal web de socios queda fuera de alcance en esta fase. La prioridad es el bot operativo (que ahorra trabajo al tesorero) antes que el portal de consulta (que ahorra llamadas de los socios).

## Consecuencias

**Ganamos:**
- Foco. El equipo no divide esfuerzo entre dos productos nuevos simultáneamente.
- La `coop-api` se diseña pensando en el portal desde ya (los endpoints de consulta ya están especificados), pero no hay que construir frontend todavía.

**Perdemos:**
- Los socios siguen dependiendo del tesorero para consultar su saldo. Esto no cambia respecto a hoy.

**Condición de revisión:** Una vez que el bot esté estable en producción, el portal web puede construirse sobre los mismos endpoints de consulta de `coop-api` sin cambios en el backend.

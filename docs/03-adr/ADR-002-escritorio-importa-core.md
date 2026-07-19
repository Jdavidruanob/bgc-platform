# ADR-002 — El escritorio importa coop-core directamente (no HTTP)

**Estado:** Decidido  
**Fecha:** 2026-07-18

---

## Contexto

Al extraer la lógica de negocio a `coop-core`, hay dos formas de que el escritorio acceda a ella: (a) importar el paquete Python directamente, o (b) convertir el escritorio en un cliente HTTP que llame a `coop-api`.

## Decisión

El escritorio importa `coop-core` como dependencia Python directa. No se reescribe como cliente HTTP.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Escritorio como cliente HTTP de coop-api | Requiere reescribir todas las vistas para manejar HTTP (errores de red, timeouts, estados de carga). La app actual tiene flujos síncronos que asumen que la operación es local. El esfuerzo es desproporcionado para el beneficio. |
| Escritorio + coop-api, pero con cliente generado desde OpenAPI | Reduce algo del boilerplate HTTP, pero el modelo de error y el manejo de estado offline siguen siendo el mismo problema. |

## Consecuencias

**Ganamos:**
- Zero reescritura de vistas.
- El escritorio sigue siendo tan rápido como antes (sin latencia HTTP).
- Una sola ruta de migración: solo cambiar la capa de repositorios.

**Perdemos:**
- El escritorio y la API pueden tener versiones de `coop-core` distintas si no se coordinan los deploys. Mitigación: uv workspace garantiza que todos los paquetes usen la misma versión del monorepo.
- Si en el futuro se quiere un escritorio web, habría que reescribirlo de todas formas. No hay lock-in real.
- El escritorio necesita acceso directo a Postgres (requiere que la PC del tesorero tenga las credenciales). Aceptable: es el mismo modelo que antes, solo cambia SQLite local por Postgres remoto.

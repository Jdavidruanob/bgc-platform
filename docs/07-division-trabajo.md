# 07 — División de trabajo

---

## Tabla de responsabilidades por paquete

| Paquete | Dueño (CODEOWNERS) | Descripción de la responsabilidad |
|---------|--------------------|-----------------------------------|
| `packages/core` | Dev A | Extracción y limpieza de servicios y repositorios. Migración a Postgres. Tests con ≥ 90 % cobertura. |
| `packages/contracts` | Dev A | Schemas Pydantic de intenciones y respuestas. Especificación OpenAPI. Mock server. |
| `packages/api` | Dev A | FastAPI. Autenticación. Resolución de entidades (fuzzy search). Idempotencia. Auditoría. |
| `packages/desktop` | Dev A | Adaptar las vistas al nuevo `coop-core`. Modo offline. Conexión a Postgres. |
| `packages/bot` | Dev B | Todo lo que ocurre entre el mensaje del usuario y la llamada HTTP a la API, más la presentación de la respuesta. |
| `docs/` | Dev A | Mantiene actualizada la documentación de arquitectura y contratos. Dev B puede proponer PR a `docs/08-onboarding-dev-b.md`. |
| `.github/` | Dev A | CI, CODEOWNERS, branch protection. |

---

## Qué hace Dev B — tareas desglosadas con estimación

Dev B trabaja **exclusivamente** sobre `packages/bot/` y contra el mock server de `packages/contracts/`.

| # | Tarea | Estimación |
|---|-------|-----------|
| B-01 | Configurar el proyecto del bot: pyproject.toml, estructura de carpetas, CI básico (lint + mypy + pytest) | 0.5 día |
| B-02 | Implementar el adaptador de Telegram (recibir mensajes de texto y audio, enviar texto y documentos) | 1 día |
| B-03 | Implementar el cliente de Whisper (descarga del audio, llamada a API, retorno de transcripción) | 0.5 día |
| B-04 | Implementar el módulo NLU (llamada a OpenAI Chat con prompt del sistema, parseo del JSON, validación contra schemas Pydantic de `coop-contracts`) | 1 día |
| B-05 | Implementar el cliente HTTP de `coop-api` (wraper sobre httpx, manejo de errores, idempotencia) | 1 día |
| B-06 | Implementar la resolución de entidades (llamada a `GET /socios?q=`, lógica de desambiguación, preguntas al operador) | 1 día |
| B-07 | Implementar la máquina de estados del diálogo (estados: esperando_mensaje → procesando → esperando_confirmación → ejecutando → respondiendo; manejo de timeout y cancelación) | 2 días |
| B-08 | Implementar la construcción del resumen de confirmación (texto legible con nombres, montos formateados, saldos) | 0.5 día |
| B-09 | Implementar el generador de PDF del comprobante (reportlab, usando los datos del response de la API) | 1 día |
| B-10 | Implementar el manejo de errores de la API (mostrar `mensaje` del error al operador, manejar 401/404/422/500 con mensajes distintos) | 0.5 día |
| B-11 | Tests unitarios: resolución de entidades, máquina de estados, construcción del resumen, generación de PDF | 1.5 días |
| B-12 | Test de integración end-to-end contra el mock server: flujo completo de aporte, retiro, pago, combinado | 1 día |
| B-13 | Implementar las consultas (saldo, cuotas, caja) | 0.5 día |
| B-14 | Configurar el despliegue en Fly.io / Railway (Dockerfile, variables de entorno, webhook de Telegram) | 1 día |
| **Total** | | **~13 días** |

---

## Orden de trabajo y punto de integración

```
Dev A                              Dev B
──────────────────────────────     ──────────────────────────────
Fase 0: Inventario ✅

Fase 1: Extraer coop-core          (Dev B espera el mock server)
  └─ Separar config.py
  └─ Limpiar DATE('now')
  └─ Adaptar repos a Postgres
  └─ Tests core ≥ 90 %

Fase 2: Publicar coop-contracts    ──▶  Dev B puede arrancar
  └─ Schemas Pydantic                   B-01 a B-05 en paralelo
  └─ Mock server levantado
  └─ openapi.yaml publicado

Fase 3: coop-api v0 (mock DB)      ──▶  Dev B puede probar B-06 a B-09
  └─ Endpoints funcionales               contra API real (staging)
  └─ Auth + idempotencia
  └─ Resolución entidades

Fase 4: Migración Postgres         ──▶  Dev B hace B-10 a B-12
  └─ Script de migración
  └─ Escritorio conectado a PG           (integración final)
  └─ Snapshot offline

▲ PUNTO DE INTEGRACIÓN ──────────────────────────────────────────
  Dev B cambia BASE_URL del mock al endpoint real de staging.
  Se corre el test suite de B-12 contra la API real.
  Dev A valida que los datos en Postgres son correctos.

Fase 5: Deploy a producción        ──▶  Dev B: deploy bot a producción
  └─ API en Fly.io/Railway               webhook de Telegram activo
  └─ Postgres en producción
```

---

## Lo que Dev B NO debe tocar

| Área | Por qué |
|------|---------|
| `packages/core/` | Contiene la lógica financiera. Cualquier PR sobre este paquete requiere aprobación de Dev A. |
| `packages/api/` | La API es responsabilidad de Dev A. Dev B solo la consume por HTTP. |
| `packages/contracts/` | Los schemas son la frontera. Si Dev B necesita un cambio de schema, propone issue y Dev A lo implementa. |
| `packages/desktop/` | Es la app existente del tesorero. Dev B no la conoce ni debe modificarla. |
| Credenciales de Postgres | Dev B nunca ve ni necesita las credenciales de la base de datos de producción. |
| Datos reales de socios | Dev B trabaja únicamente con datos ficticios del mock server. |

---

## Plan de integración: del mock a la API real

### Paso 1: Configuración por variable de entorno
```
# .env para desarrollo contra mock:
COOP_API_BASE_URL=http://localhost:8001

# .env para staging contra API real:
COOP_API_BASE_URL=https://coop-api-staging.fly.dev
```
El bot no tiene hardcoded ninguna URL. El switch es cambiar una variable.

### Paso 2: Checklist de integración

Cuando Dev A tenga la API de staging disponible:

- [ ] Dev B cambia `COOP_API_BASE_URL` al endpoint de staging.
- [ ] Dev B corre el test suite completo (`pytest packages/bot -v`).
- [ ] Dev B ejecuta manualmente el flujo completo de aporte desde Telegram real.
- [ ] Dev A verifica en Postgres que el recibo fue creado correctamente.
- [ ] Dev A verifica que el `audit_log` tiene el registro completo.
- [ ] Dev B confirma que el PDF recibido en Telegram es correcto.

### Paso 3: Criterios de aceptación del entregable de Dev B

El entregable de Dev B se considera completo cuando:

1. El bot responde a audio en español con el resumen de confirmación en ≤ 15 segundos.
2. Dado "sí" del operador, la API registra la operación y el bot entrega el PDF.
3. Dado "no" o silencio por > 5 minutos, la operación queda cancelada sin persistir nada.
4. Un mensaje con nombre ambiguo muestra la lista de candidatos correctamente.
5. Un error de la API (ej: saldo insuficiente) se muestra al operador en español sin stack trace.
6. Tests: `pytest packages/bot --cov=coop_bot --cov-fail-under=70` pasa en CI.
7. El bot corre en producción en Fly.io sin intervención manual.

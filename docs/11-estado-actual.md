# 11 — Estado actual del proyecto

> Última actualización: 2026-07-20
> Redactado por: Dev A (Jdavidruanob)
> Destinatario principal: Dev B (firerob)

---

## Resumen ejecutivo

El backend está listo para que empieces a trabajar **hoy mismo**. Tienes un mock server funcional que simula toda la API. La API real también está implementada y en revisión (PR #4), aunque para tus primeras semanas de desarrollo no la necesitas.

**Tu tarea:** implementar `packages/bot/` — todo lo que ocurre entre el mensaje del operador y la llamada HTTP a la API. La guía de arranque detallada está en `docs/08-onboarding-dev-b.md`.

---

## Estado de los paquetes

| Paquete | Estado | Ubicación | Notas |
|---------|--------|-----------|-------|
| `coop-core` | ✅ Completo y mergeado | `packages/core/` | 75 tests, 96% cob. No tocar. |
| `coop-contracts` | ✅ Completo y mergeado | `packages/contracts/` | 45 tests, 97% cob. Mock server incluido. |
| `coop-api` | ⏳ Código listo, PR #4 en revisión | `packages/api/` | 25 tests, 93% cob. Falta deploy. |
| `coop-bot` | 🔴 Sin empezar | `packages/bot/` | **Tu trabajo.** |
| `coop-desktop` | 🟡 Estructura creada | `packages/desktop/` | Será Fase 6. No tocar por ahora. |

---

## Pull Requests

| PR | Título | Estado |
|----|--------|--------|
| #1 | docs: actualizar specs con flujos reales | ✅ Mergeado |
| #2 | feat(core): extraer coop-core desde BGC-software | ✅ Mergeado |
| #3 | feat(contracts): coop-contracts + mock server | ✅ Mergeado |
| #4 | feat(api): coop-api v0 — todos los endpoints | ⏳ En revisión |

---

## Lo que el mock server ya implementa (disponible HOY)

Levántalo con:
```bash
uv run --package coop-contracts python -m coop_contracts.mock_server
# corre en http://localhost:8001
# docs interactivos: http://localhost:8001/docs
```

Header de auth requerido: `Authorization: Bearer mock-secret`

### Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check (sin auth) |
| GET | `/socios?q=pedro` | Búsqueda fuzzy de socios |
| GET | `/socios/{id}` | Datos de un socio |
| GET | `/socios/{id}/creditos` | Créditos activos |
| GET | `/creditos/{letra_id}/cuotas-pendientes` | Cuotas pendientes con mora |
| GET | `/caja` | Saldo en caja y config |
| POST | `/operaciones/aportes` | Registrar aporte(s) |
| POST | `/operaciones/retiros` | Registrar retiro |
| POST | `/operaciones/pagos` | Registrar pago de crédito |
| POST | `/operaciones/combinados` | Aporte + pago en un recibo |
| GET | `/notificaciones/pendientes` | Notificaciones sin enviar |
| PATCH | `/notificaciones/{id}` | Marcar notif como enviada/fallida |
| POST | `/test/reset` | Reiniciar estado (solo tests) |

### Datos ficticios del mock

| ID | Nombre completo | Saldo | Crédito |
|----|----------------|-------|---------|
| 1 | Pedro Antonio Gómez Ruiz | $320.000 | Letra 450 |
| 2 | Pedro Luis Gómez Castro | $150.000 | — |
| 3 | María López Herrera | $250.000 | — |
| 4 | Carmenza Suárez Peña | $180.000 | — |
| 5 | Hernando Ruiz Vargas | $500.000 | Letra 451 |

> IDs 1 y 2 son homónimos ("Pedro Gómez") → útil para probar desambiguación.

---

## Tus tareas (checklist de Dev B)

Según `docs/07-division-trabajo.md`. Las marcas ✅/🔴 son del estado al 2026-07-20.

| ID | Tarea | Estado | Notas |
|----|-------|--------|-------|
| B-01 | Setup del proyecto bot: pyproject.toml, CI | 🟡 Parcial | `pyproject.toml` existe; estructura de carpetas vacía. |
| B-02 | Adaptador Telegram | 🔴 Sin empezar | |
| B-03 | Cliente Whisper | 🔴 Sin empezar | |
| B-04 | Módulo NLU | 🔴 Sin empezar | Schemas listos en `coop_contracts.intenciones` |
| B-05 | Cliente HTTP coop-api | 🔴 Sin empezar | Schemas de request/response en `coop_contracts.respuestas` |
| B-06 | Resolución de entidades | 🔴 Sin empezar | Prueba con `GET /socios?q=` del mock |
| B-07 | Máquina de estados del diálogo | 🔴 Sin empezar | Ver `docs/07` para estados |
| B-08 | Resumen de confirmación | 🔴 Sin empezar | |
| B-09 | Generador de PDF (reportlab) | 🔴 Sin empezar | |
| B-10 | Implementaciones de `Notificador` | 🔴 Sin empezar | `MockNotificador` ya existe en `coop_contracts.notificador` |
| B-11 | Procesador de cola de notificaciones | 🔴 Sin empezar | Endpoints `/notificaciones/*` ya disponibles |
| B-12 | Manejo de errores de la API | 🔴 Sin empezar | Ver `ErrorResponse` en `coop_contracts.respuestas` |
| B-13 | Tests unitarios | 🔴 Sin empezar | Objetivo: `--cov-fail-under=70` |
| B-14 | Test E2E contra mock server | 🔴 Sin empezar | Usar `POST /test/reset` entre tests |
| B-15 | Consultas (socio, cuotas, caja) | 🔴 Sin empezar | |
| B-16 | Deploy en Fly.io / Railway | 🔴 Sin empezar | |

**Orden recomendado de arranque:** B-01 → B-05 → B-03 → B-04 → B-06 → B-07 → B-02 → B-08 → B-09 → B-15 → B-10 → B-11 → B-12 → B-13 → B-14 → B-16.

---

## Cómo hacer un aporte de prueba contra el mock (curl)

```bash
# 1. Levantar mock
uv run --package coop-contracts python -m coop_contracts.mock_server &

# 2. Buscar socios
curl -s "http://localhost:8001/socios?q=pedro" \
  -H "Authorization: Bearer mock-secret" | python3 -m json.tool

# 3. Registrar aporte (Pedro, $80.000)
curl -s -X POST "http://localhost:8001/operaciones/aportes" \
  -H "Authorization: Bearer mock-secret" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 80000}]}' \
  | python3 -m json.tool
```

---

## Cuándo cambiamos del mock a la API real

Cuando Dev A merge el PR #4 y haga el deploy a staging, te aviso con la URL de staging. Solo tendrás que cambiar en tu `.env`:

```bash
# Antes (mock local)
COOP_API_BASE_URL=http://localhost:8001
COOP_API_TOKEN=mock-secret

# Después (API staging)
COOP_API_BASE_URL=https://coop-api-staging.fly.dev
COOP_API_TOKEN=<token-que-te-paso-Dev-A>
```

No hay cambios de código en el bot. Solo cambia la variable de entorno.

---

## Lo que NO debes tocar

- `packages/core/` — lógica financiera, cualquier PR requiere aprobación de Dev A
- `packages/api/` — es responsabilidad de Dev A
- `packages/contracts/` — si necesitas un cambio de schema, abre un issue y Dev A lo implementa
- `packages/desktop/` — app del tesorero, Fase 6
- Credenciales reales de la cooperativa

---

## Puntos de contacto / convenciones

- **Rama:** crea `feat/bot/<tarea>` para cada tarea. PR a `main`, Dev A hace la revisión.
- **Commit:** usa [Conventional Commits](https://www.conventionalcommits.org/) en español, p.ej. `feat(bot): implementar cliente Whisper`
- **Schema cambio:** si el mock no modela algo que necesitas, abre un issue en GitHub describiendo qué falta. No modifiques el mock directamente.
- **Errores:** si el mock se comporta distinto a lo documentado en `docs/05`, es un bug del mock — repórtalo.

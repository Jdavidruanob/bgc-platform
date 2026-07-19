# 06 — Contratos de calidad

---

## Herramientas

| Herramienta | Propósito | Versión mínima |
|-------------|-----------|----------------|
| `uv` | Gestión de dependencias y workspace | 0.4+ |
| `ruff` | Linter + formateador | 0.5+ |
| `mypy` | Tipado estático en modo strict | 1.10+ |
| `pytest` | Tests | 8.0+ |
| `pytest-cov` | Cobertura | 5.0+ |
| `pytest-mock` | Mocks en tests | 3.14+ |

---

## Umbrales de cobertura

| Paquete | Umbral mínimo | Justificación |
|---------|---------------|---------------|
| `coop-core` | **90 %** | Contiene toda la lógica financiera. Un bug aquí afecta dinero real. El 10 % de margen cubre helpers de logging y rutas de error de infraestructura que son difíciles de testear unitariamente. |
| `coop-api` | 75 % | La mayoría del código es glue (validación de request, llamada al servicio, formateo de response). El 75 % cubre todos los caminos de negocio. El glue de FastAPI no aporta valor marginal al testearse. |
| `coop-contracts` (mock server) | 60 % | El mock server es utilidad de desarrollo. Priorizamos que sea correcto, no exhaustivamente testeado. |
| `coop-bot` | 70 % | El bot tiene lógica de diálogo y NLU que es más difícil de testear end-to-end. Se testean unitariamente: resolución de entidades, construcción del resumen de confirmación, generación de PDF. |
| `coop-desktop` | No aplica | Las vistas de PySide6 no se testean automáticamente en CI. |

---

## Definition of Done

### Para cualquier cambio en `coop-core`

- [ ] `mypy --strict` pasa sin errores.
- [ ] `ruff check` y `ruff format --check` pasan.
- [ ] Todos los tests existentes pasan.
- [ ] Se añaden tests para el nuevo comportamiento con cobertura de ramas (no solo happy path).
- [ ] Cobertura global de `coop-core` ≥ 90 % tras el cambio.
- [ ] Si el cambio modifica una firma pública de servicio o repositorio, `docs/00-inventario-actual.md` está actualizado.
- [ ] Ningún `float` introducido para montos de dinero.

### Para cualquier cambio en `coop-api`

- [ ] Todo lo anterior (mypy, ruff).
- [ ] El endpoint nuevo o modificado tiene tests de integración que cubren: happy path, error de validación, recurso no encontrado, idempotencia.
- [ ] El schema OpenAPI generado por FastAPI es consistente con `docs/05-contrato-api.md`.
- [ ] Si se añade un nuevo código de error, está documentado en `docs/05-contrato-api.md`.

### Para cualquier cambio en `coop-bot`

- [ ] mypy y ruff pasan.
- [ ] La lógica de resolución de entidades está testeada con casos de: 0 resultados, 1 resultado, múltiples resultados, homónimos.
- [ ] La máquina de estados tiene tests para: confirmación exitosa, cancelación, timeout, intención incompleta.
- [ ] El PDF generado se valida (no vacío, contiene al menos recibo_id y monto).

---

## Convención de commits

Usamos **Conventional Commits** (https://www.conventionalcommits.org/):

```
<tipo>(<scope>): <descripción en imperativo, en español>

[cuerpo opcional]

[footer opcional]
```

**Tipos permitidos:**

| Tipo | Cuándo usarlo |
|------|---------------|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `refactor` | Cambio que no agrega ni corrige, solo reorganiza |
| `test` | Solo tests, sin cambio en lógica |
| `docs` | Solo documentación |
| `chore` | Configuración, dependencias, CI |
| `perf` | Mejora de rendimiento |

**Scopes:** `core`, `api`, `bot`, `contracts`, `desktop`, `docs`, `ci`

**Ejemplos:**
```
feat(core): agregar validación de monto mínimo de retiro
fix(api): corregir propagación de ValueError en endpoint de pagos
test(core): cubrir rama de abono-cascada con mora en PagoService
docs(contratos): actualizar schema de IntRegCombinado
```

---

## Convención de ramas

| Patrón | Propósito |
|--------|-----------|
| `main` | Código en producción. Protegida. Solo merge vía PR aprobada. |
| `dev` | Integración continua. Los PRs de features se mergean aquí primero. |
| `feat/<scope>/<descripcion-corta>` | Nuevas funcionalidades |
| `fix/<scope>/<descripcion-corta>` | Correcciones |
| `chore/<descripcion-corta>` | Configuración y mantenimiento |

**Ejemplos:**
```
feat/core/migrar-repos-a-postgres
feat/bot/flujo-confirmacion
fix/api/idempotencia-pagos
```

---

## CI en GitHub Actions

### En cada `push` a cualquier rama

```yaml
jobs:
  lint:
    - ruff check packages/
    - ruff format --check packages/

  typecheck:
    - mypy packages/core/src packages/api/src packages/bot/src packages/contracts/src

  test-core:
    - pytest packages/core --cov=coop_core --cov-fail-under=90

  test-api:
    - pytest packages/api --cov=coop_api --cov-fail-under=75

  test-bot:
    - pytest packages/bot --cov=coop_bot --cov-fail-under=70
```

### Qué bloquea el merge a `main` / `dev`

- Cualquier fallo en `lint`, `typecheck`, `test-core`, `test-api`, `test-bot`.
- Cobertura por debajo del umbral.
- PR sobre paquetes de Dev A sin aprobación de Dev A (CODEOWNERS).

### Lo que NO corre en CI

- Tests del escritorio PySide6 (requieren pantalla virtual; excluido por complejidad).
- Tests end-to-end con Telegram real (requieren token de bot activo).
- Tests contra Postgres real (se usa SQLite en memoria para los tests de `coop-core`; se usa una DB Postgres de test para `coop-api` si el CI tiene el servicio disponible).

---

## Política de manejo de dinero: enteros

**Regla:** Todo monto de dinero (pesos colombianos) es `int`. Nunca `float`.

**En código Python:**
- Los tipos de los parámetros y retornos de servicios usan `int` explícito.
- `mypy --strict` rechaza `float` donde se espera `int`.
- El cálculo de intereses: `int(round(saldo * tasa))` — la multiplicación puede ser `float`, pero se convierte a `int` inmediatamente.
- La mora: `int(valor_cuota * tasa_mora)` — ídem.

**En la base de datos:**
- Todos los campos de monto son `INTEGER` (Postgres: `BIGINT`).
- La tasa de interés (`creditos.interes`) se guarda como `NUMERIC(5,4)` en Postgres (vs `REAL` actual en SQLite). Esto evita imprecisiones de punto flotante al leer y escribir la tasa.

**Verificación en el código actual (hallazgo del inventario):**
Los servicios existentes ya cumplen esta política. Ningún monto se almacena como `float`. La tasa de interés usa `float` (aceptable para una tasa, no un monto). ✅

---

## Política de logs y auditoría de operaciones por voz

Cada operación originada en el bot genera un registro de auditoría **antes** de ejecutar el commit. El registro es inmutable (solo insert, nunca update/delete).

### Tabla de auditoría (en `coop-api`)

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    canal           TEXT NOT NULL DEFAULT 'bot',   -- 'bot' | 'desktop' | 'api'
    operador        TEXT NOT NULL,                 -- chat_id de Telegram
    audio_url       TEXT,                          -- URL del archivo de audio (nullable si es texto)
    transcripcion   TEXT,                          -- texto transcrito por Whisper
    intencion_json  JSONB,                         -- JSON producido por el LLM
    endpoint        TEXT NOT NULL,                 -- '/operaciones/aportes'
    idempotency_key TEXT NOT NULL,
    request_payload JSONB NOT NULL,                -- payload enviado a la API (sin passwords)
    response_status INT,                           -- 201, 422, etc.
    operacion_id    BIGINT,                        -- recibo_id o letra_id resultante (nullable si falló)
    error_codigo    TEXT,                          -- código de error si falló
    duracion_ms     INT                            -- tiempo total del flujo bot→api
);
```

### Qué se registra y cuándo

| Momento | Qué se guarda |
|---------|--------------|
| Al recibir audio | `audio_url`, `operador`, `created_at` |
| Tras transcripción | `transcripcion` |
| Tras NLU | `intencion_json` |
| Al enviar a la API | `endpoint`, `request_payload`, `idempotency_key` |
| Al recibir response | `response_status`, `operacion_id` o `error_codigo`, `duracion_ms` |

El registro es creado al inicio del flujo y actualizado progresivamente. Si el flujo falla en cualquier punto, el registro queda con los campos disponibles hasta ese momento.

### Qué NO se guarda

- Mensajes de confirmación/cancelación del operador (solo relevante dentro de la sesión).
- Datos personales de socios más allá de los IDs (el `request_payload` contiene IDs, no nombres).
- Audio en la propia DB (solo la URL del archivo guardado en storage externo o en el filesystem del bot).

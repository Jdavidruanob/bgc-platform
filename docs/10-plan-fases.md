# 10 — Plan de fases

> Cada fase termina en un estado funcional y verificable.
> El punto de no retorno de la migración a Postgres está marcado explícitamente.

---

## Visión general

```
Fase 0: Inventario ✅ (completado)
Fase 1: coop-core extraído, limpio y testeado (SQLite)
Fase 2: coop-contracts + mock server publicados → Dev B arranca
Fase 3: coop-api funcional en staging (con Postgres de staging)
Fase 4: Migración a Postgres ← PUNTO DE NO RETORNO
Fase 5: Bot completo integrado + deploy a producción
Fase 6: Escritorio conectado a Postgres en producción
```

---

## Fase 0 — Inventario ✅

**Estado:** Completado (2026-07-18)  
**Entregable:** `docs/00-inventario-actual.md`

---

## Fase 1 — Extracción de `coop-core`

**Objetivo:** `packages/core/` contiene los servicios y repositorios extraídos de `BGC-software/`, libres de Qt, testeables sin sistema de archivos.

**Condición de entrada:** Fase 0 completada.

**Tareas:**
1. Separar `config.py` en tres partes:
   - `packages/core/src/coop_core/utils/fecha.py` — `get_hoy`, `get_hoy_str`, `set_fecha_simulada`
   - `packages/core/src/coop_core/utils/formato.py` — `format_miles_colombian_int`, `format_full_name_for_excel`
   - `packages/desktop/src/coop_desktop/config.py` — rutas, colores, funciones Qt
2. Copiar y adaptar los repositorios: reemplazar `sqlite3` por interfaz abstracta; eliminar `DATE('now')`.
3. Copiar y adaptar los servicios: eliminar retornos de `excel_path`; retornar dicts de datos.
4. Consolidar `CreditosRepository.register_complete` para usar `amortization.build_amortization_schedule`.
5. Extraer helpers duplicados de `CombinadoService` a módulo compartido con `PagoService`.
6. Escribir tests con cobertura ≥ 90 % usando SQLite en memoria como DB de test.

**Condición de salida verificable:**
```bash
uv run pytest packages/core --cov=coop_core --cov-fail-under=90
uv run mypy packages/core/src --strict
uv run python -c "from coop_core.services.aporte_service import AporteService; print('OK')"
# El import anterior NO debe instalar ni importar PySide6
```

**Duración estimada:** 3–4 días (Dev A)

---

## Fase 2 — `coop-contracts` + mock server

**Objetivo:** Dev B tiene todo lo que necesita para arrancar sin esperar a la API real.

**Condición de entrada:** Fase 1 completada.

**Tareas:**
1. Crear `packages/contracts/src/coop_contracts/intenciones.py` con los schemas Pydantic del `docs/04-contrato-intenciones.md`.
2. Crear `packages/contracts/src/coop_contracts/respuestas.py` con los schemas de response.
3. Crear `packages/contracts/src/coop_contracts/mock_server.py`: FastAPI app que devuelve datos ficticios para todos los endpoints de `docs/05-contrato-api.md`.
4. Crear `packages/contracts/src/coop_contracts/mock_data.py`: socios y créditos ficticios (los 5 socios del onboarding).
5. Verificar que `uv run --package coop-contracts python -m coop_contracts.mock_server` levanta en puerto 8001.
6. Publicar la rama en GitHub y notificar a Dev B.

**Condición de salida verificable:**
```bash
# Mock server responde correctamente:
curl http://localhost:8001/health
curl http://localhost:8001/socios?q=pedro
curl -X POST http://localhost:8001/operaciones/aportes \
     -H "Authorization: Bearer dev-secret" \
     -H "Idempotency-Key: test-1" \
     -H "Content-Type: application/json" \
     -d '{"recibi_de_id": 1, "aportes": [{"socio_id": 1, "monto": 80000}]}'
```

**Duración estimada:** 1–2 días (Dev A) + Dev B arranca en paralelo

---

## Fase 3 — `coop-api` en staging

**Objetivo:** La API real funciona en un entorno de staging con Postgres de staging (no datos reales).

**Condición de entrada:** Fase 1 completada. Fase 2 en paralelo (Dev B ya trabaja).

**Tareas:**
1. Implementar `packages/api/src/coop_api/`:
   - Autenticación por Bearer token estático.
   - Endpoint `GET /socios?q=` con fuzzy match (rapidfuzz).
   - Todos los endpoints de operación (POST /operaciones/*) llamando a los servicios de `coop-core`.
   - Idempotencia con tabla `idempotency_keys` en Postgres.
   - Tabla `audit_log` y escritura de cada operación.
   - Formato uniforme de errores (ErrorResponse).
2. Configurar Postgres de staging en Fly.io o Railway.
3. Deploy de la API en staging.
4. Correr tests de API contra Postgres de staging.

**Condición de salida verificable:**
```bash
uv run pytest packages/api --cov=coop_api --cov-fail-under=75
# Tests de integración corriendo contra Postgres de staging pasan.
curl https://coop-api-staging.fly.dev/health  # → {"status": "ok"}
```

**Duración estimada:** 3–4 días (Dev A)

---

## Fase 4 — Migración a Postgres en producción

### ⚠️ PUNTO DE NO RETORNO

A partir de este punto, **Postgres es la fuente de verdad**. La SQLite de producción queda como archivo de respaldo, pero no se escribe en ella.

**Condición de entrada:** Fase 3 completada y validada. Dev A tiene backup de la SQLite de producción.

**Plan de migración:**

```
1. [Pre-migración] Backup de la SQLite:
   cp BGC-software.db BGC-software-backup-$(date +%Y%m%d).db

2. Correr script de migración en staging primero:
   uv run python scripts/migrate_sqlite_to_postgres.py \
     --sqlite BGC-software.db \
     --postgres $DATABASE_URL_STAGING

3. Verificaciones post-migración en staging:
   - Suma de socios.saldo == config.saldo_en_caja
   - Número de cuotas pagadas == cuotas con fecha_pago NOT NULL
   - Número de créditos activos == expected
   - Últimos 10 registros del auxiliar coinciden entre SQLite y Postgres

4. Si todo OK → correr migración en producción:
   uv run python scripts/migrate_sqlite_to_postgres.py \
     --sqlite BGC-software.db \
     --postgres $DATABASE_URL_PROD

5. Verificaciones post-migración en producción (mismos checks).

6. Apuntar el escritorio a Postgres (cambiar DATABASE_URL).

7. Hacer UNA operación de prueba desde el escritorio (aporte de $1 al tesorero,
   verificar que aparece en Postgres, luego ajustar o revertir).
```

### Plan de rollback

Si la migración introduce datos incorrectos:

1. Detener el escritorio inmediatamente.
2. Revertir la variable `DATABASE_URL` del escritorio a la SQLite local.
3. El escritorio vuelve a funcionar con la SQLite original (sin pérdida de datos previos a la migración).
4. Las operaciones hechas en Postgres entre la migración y el rollback se pierden (por eso la ventana de migración debe ser pequeña y verificada).

> La ventana de migración debe ocurrir cuando no haya operaciones pendientes (ej: un día sin reunión de cobro). Duración estimada del proceso: 15–30 minutos.

**Condición de salida verificable:**
- El escritorio opera normalmente con Postgres.
- La API de staging apunta a la misma DB que el escritorio y lee los datos correctos.
- El script de verificación post-migración pasa sin errores.

**Duración estimada:** 1 día (Dev A)

---

## Fase 5 — Bot completo en producción

**Objetivo:** El bot está desplegado, el operador puede usarlo desde Telegram.

**Condición de entrada:** Fases 3 y 4 completadas. Dev B tiene el bot listo (tareas B-01 a B-14 del `docs/07-division-trabajo.md`).

**Tareas:**
1. Dev B: deploy del bot en Fly.io / Railway.
2. Dev B: configurar webhook de Telegram apuntando al servidor de producción.
3. Dev A: cambiar `COOP_API_BASE_URL` del bot de staging a producción.
4. Prueba de humo: operador envía un audio de prueba desde el Telegram real.
5. Verificar que el `audit_log` tiene el registro completo de la operación de prueba.
6. Verificar que el PDF llega correctamente.

**Condición de salida verificable:**
- El operador completa un flujo de aporte real desde Telegram.
- El recibo aparece en Postgres.
- El PDF llega al chat de Telegram del operador.
- El escritorio muestra el mismo recibo en el historial.

**Duración estimada:** 1–2 días (Dev A + Dev B en paralelo)

---

## Fase 6 — Escritorio conectado a Postgres en producción + modo offline

**Objetivo:** El escritorio usa Postgres y tiene el snapshot de solo lectura operativo.

**Condición de entrada:** Fase 4 completada.

**Tareas:**
1. Implementar `DBConnection` para Postgres en `packages/desktop/`.
2. Implementar la lógica de snapshot: al conectar, copiar las tablas relevantes a SQLite local.
3. Implementar el detector de conectividad: si no hay internet, abrir en modo solo-lectura.
4. Deshabilitar los botones de escritura en modo offline.
5. Mostrar el timestamp del último refresh del snapshot.
6. Configurar el refresh automático cada 30 minutos.

**Condición de salida verificable:**
- El tesorero desconecta el WiFi y la app sigue abriendo (modo lectura).
- Con WiFi, el tesorero registra un aporte, reconecta el escritorio y el aporte aparece.
- El bot registra otro aporte, el escritorio (con WiFi) lo muestra en el historial después del próximo refresh.

**Duración estimada:** 2–3 días (Dev A)

---

## Resumen de fases y dependencias

```
Fase 1 (core)
    │
    ├──── Fase 2 (contracts + mock) ──────────▶ Dev B arranca
    │                                                │
    └──── Fase 3 (api staging) ──────────────────────┤
              │                                      │
              └──── Fase 4 (migración PG) ◀─ NO RETORNO
                        │
                        ├──── Fase 5 (bot producción) ◀── Dev B (en paralelo)
                        │
                        └──── Fase 6 (escritorio PG + offline)
```

**Duración total estimada (Dev A solo + Dev B en paralelo desde Fase 2):**
- Dev A: ~15 días de trabajo
- Dev B: ~13 días de trabajo (desde Fase 2)
- Elapsed con paralelismo: ~3–4 semanas

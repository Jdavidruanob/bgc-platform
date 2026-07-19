# ADR-001 — Migrar de SQLite a PostgreSQL en la nube

**Estado:** Decidido  
**Fecha:** 2026-07-18

---

## Contexto

La app de escritorio usa SQLite: un archivo `.db` local por año fiscal. Esto funciona para un solo usuario en la PC del tesorero. Al añadir la API y el bot, necesitamos que múltiples procesos (escritorio + bot) lean y escriban sobre la misma fuente de verdad de forma segura. SQLite no es adecuado para acceso concurrente desde procesos en máquinas distintas.

## Decisión

Migrar a PostgreSQL gestionado en la nube (Neon, Fly Postgres o Railway). Una sola base de datos para toda la plataforma. Solo cambia la capa de repositorios; los servicios en `coop-core` no se tocan más allá de eliminar el SQL SQLite-específico (`DATE('now')`, `sqlite_sequence`).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Mantener SQLite + sincronización | Reintroduce conflictos de escritura entre procesos. Incompatible con el diseño de múltiples clientes. |
| MySQL / MariaDB | Compatible técnicamente, pero el ecosistema Python (psycopg3, SQLAlchemy) prioriza Postgres. Sin ventaja real para este caso. |
| Turso (SQLite distribuido) | Interesante, pero añade complejidad de replicación sin beneficio real a esta escala. |
| Supabase | Postgres gestionado pero con superficie de ataque mayor (auth, storage, realtime que no usamos). Neon/Fly es más simple. |

## Consecuencias

**Ganamos:**
- Acceso concurrente seguro desde escritorio + bot.
- Transacciones ACID reales con aislamiento de lectura.
- Backups automáticos del proveedor.
- Tipos de datos nativos: `DATE`, `NUMERIC`, `BOOLEAN` (vs todo-texto en SQLite config).

**Perdemos:**
- El archivo SQLite es el backup más simple del mundo: `cp BGC.db backup.db`. Con Postgres en la nube dependemos del proveedor para backups.
- Requiere conexión a internet para cualquier escritura (mitigado por el snapshot local de solo lectura).
- Costo mensual (~USD 0–6 según proveedor vs USD 0 con SQLite).
- La migración de datos históricos requiere un script cuidadoso (ver `docs/10-plan-fases.md`).

**Cambios de código obligatorios antes de migrar:**
1. `db/connection.py`: reemplazar `sqlite3.connect()` por `psycopg3.connect()`.
2. Todos los SQL con `DATE('now')`: reemplazar por parámetro Python (`get_hoy_str()`).
3. `schema.py`: `AUTOINCREMENT` → `GENERATED ALWAYS AS IDENTITY`; `INTEGER PRIMARY KEY` → `BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY`.
4. `config` table: opcional mejorar a columnas tipadas o mantener como clave-valor.
5. `sqlite_sequence`: eliminar toda referencia.

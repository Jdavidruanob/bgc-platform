# AGENTS.md — Guía para agentes de IA en este repositorio

## Identidad de commits — regla crítica

**NUNCA** incluyas trailers de co-autoría en los commits:

```
# ❌ Prohibido — hace que Claude aparezca como colaborador
Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Claude Sonnet <claude@anthropic.com>

# ✅ Correcto — commit limpio, solo el autor del repo
```

No modifiques `git config` (ni `user.name` ni `user.email`). Usa la configuración global existente sin tocarla.

## Mensajes de commit

Sigue Conventional Commits en español, verbo en imperativo:

```
<tipo>(<scope>): <descripción>
```

Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`  
Scopes: `core`, `api`, `bot`, `contracts`, `desktop`, `docs`, `ci`

```bash
# ✅ Ejemplos correctos
feat(core): agregar validación de monto mínimo de retiro
fix(api): corregir propagación de ValueError en pagos
docs(contratos): actualizar schema de IntCrearCredito

# ❌ Prohibido
"Updated files"
"Fix bug"
"Co-Authored-By: ..."
```

## Flujo de trabajo con GitHub

- **Nunca hagas push directo a `main`.** Crea una rama y abre un PR.
- Rama de feature: `feat/<scope>/<descripcion-corta>`
- Rama de fix: `fix/<scope>/<descripcion-corta>`
- Los cambios en `packages/core/`, `packages/api/`, `packages/contracts/`, `packages/desktop/`, `docs/` y `.github/` **requieren aprobación de @Jdavidruanob** antes de mergear. CODEOWNERS lo hace cumplir automáticamente.
- Los cambios en `packages/bot/` son propiedad de @firerob.

## Calidad de código

### Antes de cada commit, verifica:

```bash
uv run ruff check packages/
uv run ruff format --check packages/
uv run mypy packages/core/src packages/api/src packages/bot/src packages/contracts/src
```

### Antes de abrir un PR, verifica:

```bash
uv run pytest packages/core --cov=coop_core --cov-fail-under=90
uv run pytest packages/api --cov=coop_api --cov-fail-under=75
uv run pytest packages/bot --cov=coop_bot --cov-fail-under=70
```

### Reglas de código

- **Nunca uses `float` para montos de dinero.** Todo monto es `int` (pesos colombianos enteros).
- **Nunca ignores errores de mypy** con `# type: ignore` sin comentario que explique por qué.
- **Nunca hardcodees credenciales, tokens ni URLs de producción** en el código. Usa variables de entorno.
- **No agregues dependencias nuevas** sin justificar por qué la alternativa más simple no alcanza.

## Estructura del proyecto

```
packages/core/       Lógica financiera. Propietario: @Jdavidruanob. No tocar sin aprobación.
packages/contracts/  Schemas y mock server. Propietario: @Jdavidruanob.
packages/api/        FastAPI. Propietario: @Jdavidruanob.
packages/desktop/    App PySide6. Propietario: @Jdavidruanob.
packages/bot/        Bot de Telegram + Notificador WhatsApp. Propietario: @firerob.
docs/                Especificaciones. Propietario: @Jdavidruanob.
```

## Contexto del dominio

Este es el sistema de gestión de una cooperativa de ahorro y crédito familiar (~50 socios).
Opera con dinero real de personas reales. Prioriza la corrección sobre la elegancia.

- Toda operación que mueve dinero requiere confirmación explícita del operador antes de persistirse.
- Los errores de validación del dominio se expresan en español colombiano claro.
- Las notificaciones a socios (WhatsApp) nunca son bloqueantes: si fallan, se registra el fallo y la operación continúa.

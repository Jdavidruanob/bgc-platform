# ADR-007 — Monorepo único con uv workspaces

**Estado:** Propuesto  
**Fecha:** 2026-07-18

---

## Contexto

El prompt original planteaba cuatro repositorios separados (`coop-core`, `coop-api`, `coop-bot`, `coop-contracts`). La revisión posterior lo cambió a un monorepo `tesoro/` con paquetes internos gestionados por uv workspaces. Esta ADR documenta esa decisión revisada.

## Decisión

Un solo repositorio Git con cinco paquetes Python internos en `packages/`. Ambos desarrolladores tienen acceso de lectura a todo el repositorio; la separación de responsabilidades se implementa mediante CODEOWNERS (no mediante acceso Git diferenciado). uv workspaces gestiona las dependencias entre paquetes sin publicar nada a PyPI.

## Alternativas consideradas

| Alternativa | Trade-offs |
|-------------|-----------|
| Repositorios separados por paquete | Ventaja real de aislamiento (Dev B nunca vería el código de core aunque quisiera). Desventaja: coordinar cambios que cruzan paquetes requiere PRs en múltiples repos y versiones publicadas. Para un equipo de 2 personas es sobrecarga pura. |
| Monorepo con pip + editable installs | Funciona, pero sin la gestión de workspace de uv. uv resuelve el grafo de dependencias entre paquetes locales de forma nativa y es más rápido. |
| Poetry monorepo | Poetry no tiene soporte nativo de workspaces al nivel de uv. Requiere plugins. |

## Consecuencias

**Ganamos:**
- Un solo `git clone`, un solo CI, un solo entorno de desarrollo.
- Los cambios que afectan core + api + contratos se hacen en un solo PR con visibilidad completa.
- CODEOWNERS garantiza que Dev B no puede mergear cambios en paquetes de Dev A sin aprobación.

**Perdemos:**
- Dev B puede leer el código de `coop-core`. En el modelo original de repos separados, esto era imposible. En el modelo actual es un contrato social ("no debes", no "no puedes"). Si la confidencialidad del código es crítica, habría que volver a repos separados.
- El repositorio contiene tanto código de producción del tesorero como código del bot. Un leak del repo expone más.

**Nota sobre CODEOWNERS:**
Para que CODEOWNERS tenga efecto real, la rama `main` debe tener una branch protection rule en GitHub con "Require review from Code Owners" activada. Sin esa configuración, CODEOWNERS es solo documentación.

# ADR-008 — Los comprobantes se generan en la capa de presentación, no en los servicios

**Estado:** Propuesto  
**Fecha:** 2026-07-18

---

## Contexto

Los servicios actuales retornan `(recibo_id, excel_path)`. El generador de Excel está acoplado a `config.py` (que importa PySide6) y a las plantillas `.xlsx` en `ASSETS_DIR`. Esto hace que los servicios sean testeables solo si hay un sistema de archivos con las plantillas y PySide6 instalado.

## Decisión

Al extraer a `coop-core`, los servicios dejan de retornar `excel_path`. En cambio, retornan un dict con los datos estructurados del comprobante. Cada cliente decide cómo presentarlo:

- `packages/desktop/`: genera Excel con openpyxl (comportamiento actual).
- `packages/bot/`: genera PDF con reportlab.
- `packages/api/`: retorna JSON (los datos del comprobante están en el response body).

Firmas nuevas de los servicios en `coop-core`:
```python
AporteService.register(...)    -> dict  # datos del comprobante de aporte
RetiroService.register(...)    -> dict  # datos del comprobante de retiro
CreditoService.create(...)     -> dict  # datos de la tabla de amortización
PagoService.register(...)      -> dict  # datos del comprobante de pago
CombinadoService.register(...) -> dict  # datos del comprobante combinado
```

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Mantener la generación de Excel en los servicios | `coop-core` quedaría acoplado a openpyxl, a PySide6 (por `config.py`) y al sistema de archivos. Los tests de servicios requerirían plantillas .xlsx. Imposible de testear en CI limpio. |
| Generar PDF en coop-core | Acopla el core a reportlab. El bot necesita PDF pero la API no. El escritorio necesita Excel pero no PDF. El core no debería conocer el formato de presentación. |

## Consecuencias

**Ganamos:**
- Los servicios de `coop-core` son testeables sin sistema de archivos ni Qt.
- Cada cliente genera su formato nativo sin compromisos.
- Desacoplamiento limpio: los servicios no tienen dependencias de presentación.

**Perdemos:**
- Hay que refactorizar las firmas de retorno de todos los servicios. Es trabajo concreto pero acotado (6 servicios).
- Las vistas del escritorio deben adaptarse: en lugar de recibir `excel_path` directamente, reciben datos y llaman al generador. Cambio pequeño pero real.

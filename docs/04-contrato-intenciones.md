# 04 — Contrato de intenciones (NLU → API)

> Este documento define el contrato entre el LLM y la API.
> El LLM produce JSON. La API valida y ejecuta. El LLM nunca calcula ni decide.

---

## Principios del contrato

1. **El LLM solo extrae lo que el usuario dijo.** Si el usuario dijo "cien mil", el LLM escribe `100000`. No infiere, no calcula, no asume.
2. **Campos que el LLM NUNCA debe completar:** `socio_id`, `recibo_id`, `letra_id` (IDs internos), saldos, intereses calculados, montos de mora. Estos los resuelve el backend.
3. **Si falta información obligatoria, el LLM produce intención `incompleta`**, no inventa el valor.
4. **Si la intención no está en el catálogo, el LLM produce `desconocida`.**
5. **Montos siempre como enteros en pesos colombianos.** "ochenta mil" → `80000`, "cien" → `100000`.

---

## Catálogo de intenciones

| Intención | Servicio en coop-core | Requiere confirmación |
|-----------|-----------------------|-----------------------|
| `registrar_aporte` | `AporteService.register` | Sí |
| `registrar_retiro` | `RetiroService.register` | Sí |
| `registrar_pago` | `PagoService.register` | Sí |
| `registrar_combinado` | `CombinadoService.register` | Sí |
| `consultar_saldo` | `SociosRepository.get_balance` | No |
| `consultar_cuotas` | `LiquidacionesRepository.find_pending` | No |
| `consultar_caja` | `CajaService.get_saldo_caja` | No |
| `desconocida` | — | No aplica |
| `incompleta` | — | No aplica |
| `ambigua` | — | No aplica |

---

## Schemas Pydantic

```python
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Annotated

# ── Tipos base ──────────────────────────────────────────────────────────────

class AporteItem(BaseModel):
    nombre: str = Field(..., description="Nombre del socio tal como fue mencionado")
    monto: Annotated[int, Field(gt=0)] = Field(..., description="Monto en pesos enteros")

class PagoItem(BaseModel):
    nombre: str
    # El LLM NO completa letra_id. El bot lo resuelve después de identificar al socio.
    letra_id_hint: str | None = Field(
        None,
        description="Número de letra si el usuario lo mencionó explícitamente. Ej: 'letra 450'. Null si no se mencionó."
    )
    n_cuotas: Annotated[int, Field(ge=0)] = 0
    abono_capital: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validar_modo_pago(self) -> "PagoItem":
        if self.n_cuotas > 0 and self.abono_capital > 0:
            raise ValueError("n_cuotas y abono_capital son excluyentes")
        if self.n_cuotas == 0 and self.abono_capital == 0:
            raise ValueError("Debe especificarse n_cuotas o abono_capital")
        return self

# ── Intenciones de escritura ─────────────────────────────────────────────────

class IntRegAporte(BaseModel):
    intencion: Literal["registrar_aporte"]
    recibi_de: str = Field(..., description="Nombre del socio que entrega el dinero físicamente")
    aportes: list[AporteItem] = Field(..., min_length=1)
    # El LLM NO completa count_cobrables. El bot lo calcula según reglas de negocio.

class IntRegRetiro(BaseModel):
    intencion: Literal["registrar_retiro"]
    socio: str = Field(..., description="Nombre del socio que retira")
    monto: Annotated[int, Field(gt=0)]

class IntRegPago(BaseModel):
    intencion: Literal["registrar_pago"]
    recibi_de: str
    pagos: list[PagoItem] = Field(..., min_length=1)

class IntRegCombinado(BaseModel):
    intencion: Literal["registrar_combinado"]
    recibi_de: str
    aportes: list[AporteItem]
    pagos: list[PagoItem]

    @model_validator(mode="after")
    def al_menos_una_operacion(self) -> "IntRegCombinado":
        if not self.aportes and not self.pagos:
            raise ValueError("Debe haber al menos un aporte o un pago")
        return self

# ── Intenciones de consulta ──────────────────────────────────────────────────

class IntConsultarSaldo(BaseModel):
    intencion: Literal["consultar_saldo"]
    socio: str

class IntConsultarCuotas(BaseModel):
    intencion: Literal["consultar_cuotas"]
    socio: str
    letra_id_hint: str | None = None  # si el usuario mencionó la letra

class IntConsultarCaja(BaseModel):
    intencion: Literal["consultar_caja"]

# ── Intenciones de manejo de error ──────────────────────────────────────────

class IntDesconocida(BaseModel):
    intencion: Literal["desconocida"]
    texto_original: str

class IntIncompleta(BaseModel):
    intencion: Literal["incompleta"]
    intencion_detectada: str = Field(..., description="Intención que se detectó pero está incompleta")
    campos_faltantes: list[str] = Field(..., description="Qué falta para completar la operación")
    texto_original: str

class IntAmbigua(BaseModel):
    intencion: Literal["ambigua"]
    posibles_intenciones: list[str]
    texto_original: str

# ── Union discriminada ───────────────────────────────────────────────────────

from typing import Union
Intencion = Union[
    IntRegAporte, IntRegRetiro, IntRegPago, IntRegCombinado,
    IntConsultarSaldo, IntConsultarCuotas, IntConsultarCaja,
    IntDesconocida, IntIncompleta, IntAmbigua,
]
```

---

## Campos que el LLM puede completar vs. campos prohibidos

| Campo | LLM puede? | Quién lo completa |
|-------|-----------|-------------------|
| `intencion` | ✅ Sí | LLM |
| `nombre` / `recibi_de` / `socio` | ✅ Sí (textual) | LLM |
| `monto` (lo que el usuario dijo) | ✅ Sí | LLM |
| `n_cuotas` (lo que el usuario dijo) | ✅ Sí | LLM |
| `abono_capital` (lo que el usuario dijo) | ✅ Sí | LLM |
| `letra_id_hint` (si el usuario lo mencionó) | ✅ Solo si fue mencionado | LLM |
| `campos_faltantes` | ✅ Sí | LLM |
| `socio_id` | ❌ Prohibido | Bot (resolución de entidades) |
| `recibo_id` | ❌ Prohibido | Backend |
| `letra_id` (el ID real) | ❌ Prohibido | Bot (resolución post-ID del socio) |
| `saldo_actual` | ❌ Prohibido | Backend |
| `interes` calculado | ❌ Prohibido | `coop-core` |
| `mora` calculada | ❌ Prohibido | `coop-core` |
| `count_cobrables` | ❌ Prohibido | API (consulta lista de exentos en `coop-core`) |

---

## Manejo de intención desconocida, ambigua o incompleta

### Desconocida

El LLM no reconoce la intención. El bot responde:
> "No entendí esa operación. Puedo registrar: aportes, retiros, pagos de crédito. También puedo consultar saldos y cuotas. ¿Puedes reformularlo?"

### Ambigua

El LLM detecta múltiples interpretaciones posibles. El bot pregunta:
> "¿Quisiste decir (1) registrar un aporte o (2) registrar un pago?"

### Incompleta

Falta información obligatoria. El bot solicita exactamente lo que falta:
> "Entendí que quieres registrar un aporte, pero no mencionaste el monto. ¿Cuánto fue el aporte de [nombre]?"

El bot puede hacer hasta **2 preguntas de aclaración** por mensaje original. Si después de esas 2 preguntas la intención sigue incompleta, cancela y pide reformular desde cero.

---

## Política de resolución de entidades

### Flujo de resolución de nombre → socio_id

```
nombre_en_JSON
      │
      ▼
GET /socios?q={nombre}
      │
      ├── 1 resultado con score ≥ 0.85 → usar ese ID automáticamente
      │
      ├── 2–4 resultados → presentar lista al operador para elegir
      │       "¿A cuál de estos te refieres?
      │        (1) Pedro Antonio Gómez
      │        (2) Pedro Luis Gómez"
      │
      ├── 0 resultados → preguntar "No encontré a '[nombre]' en el padrón. ¿Puedes dar más apellido?"
      │
      └── 5+ resultados → "Hay demasiados socios con ese nombre. Por favor sé más específico."
```

### Umbral de fuzzy match

- Match exacto (normalizado sin tildes, case-insensitive): score 1.0 → resolución automática.
- Match parcial fuerte (ej: "Pedro Gómez" encuentra "Pedro Antonio Gómez Ruiz"): score ≥ 0.85 → resolución automática si es único.
- Matches múltiples con score ≥ 0.70: presentar opciones.
- Sin matches con score ≥ 0.70: reportar no encontrado.

El algoritmo concreto es responsabilidad de `coop-api` (endpoint `GET /socios?q=`). El bot solo interpreta la respuesta.

### Homónimos

Si hay dos socios con nombres idénticos o muy similares, el bot **siempre** presenta la lista para desambiguar, incluso si el score del primero es 1.0. El criterio: si hay más de un candidato con score ≥ 0.85, se pide confirmación.

---

## Ejemplos: frases en español colombiano coloquial → JSON esperado

### `registrar_aporte`

**Frase 1:** "Le recibí a Pedro Gómez su ahorro de cien mil"
```json
{
  "intencion": "registrar_aporte",
  "recibi_de": "Pedro Gómez",
  "aportes": [{"nombre": "Pedro Gómez", "monto": 100000}]
}
```

**Frase 2:** "Nos llegó el aporte de Carmenza y de su hija, ochenta cada una"
```json
{
  "intencion": "registrar_aporte",
  "recibi_de": "Carmenza",
  "aportes": [
    {"nombre": "Carmenza", "monto": 80000},
    {"nombre": "hija de Carmenza", "monto": 80000}
  ]
}
```
> Nota: "hija de Carmenza" quedará sin resolver hasta la desambiguación. El bot preguntará "¿A cuál socio te refieres con 'hija de Carmenza'?"

**Frase 3:** "Recibí a don Hernando, él trajo su cuota y la de la señora Martha y don Carlos, a todos les cobré ochenta"
```json
{
  "intencion": "registrar_aporte",
  "recibi_de": "Hernando",
  "aportes": [
    {"nombre": "Hernando", "monto": 80000},
    {"nombre": "Martha", "monto": 80000},
    {"nombre": "Carlos", "monto": 80000}
  ]
}
```

---

### `registrar_retiro`

**Frase 1:** "Juan Ruiz retiró doscientos mil"
```json
{"intencion": "registrar_retiro", "socio": "Juan Ruiz", "monto": 200000}
```

**Frase 2:** "La señora Rosa pidió que le sacáramos ciento cincuenta"
```json
{"intencion": "registrar_retiro", "socio": "Rosa", "monto": 150000}
```

**Frase 3:** "Me tocó devolverle quinientos mil a don Álvaro Torres"
```json
{"intencion": "registrar_retiro", "socio": "Álvaro Torres", "monto": 500000}
```

---

### `registrar_pago`

**Frase 1:** "Carlos pagó dos cuotas del crédito"
```json
{
  "intencion": "registrar_pago",
  "recibi_de": "Carlos",
  "pagos": [{"nombre": "Carlos", "n_cuotas": 2, "abono_capital": 0}]
}
```

**Frase 2:** "Don Héctor abonó trescientos mil a capital de la letra cuatrocientos cincuenta"
```json
{
  "intencion": "registrar_pago",
  "recibi_de": "Héctor",
  "pagos": [{"nombre": "Héctor", "letra_id_hint": "450", "n_cuotas": 0, "abono_capital": 300000}]
}
```

**Frase 3:** "Le recibí a María tres cuotas de la letra 448 y a su esposo dos cuotas"
```json
{
  "intencion": "registrar_pago",
  "recibi_de": "María",
  "pagos": [
    {"nombre": "María", "letra_id_hint": "448", "n_cuotas": 3, "abono_capital": 0},
    {"nombre": "esposo de María", "n_cuotas": 2, "abono_capital": 0}
  ]
}
```

---

### `registrar_combinado`

**Frase 1:** "Pedro trajo el ahorro y además pagó una cuota"
```json
{
  "intencion": "incompleta",
  "intencion_detectada": "registrar_combinado",
  "campos_faltantes": ["aportes[0].monto"],
  "texto_original": "Pedro trajo el ahorro y además pagó una cuota"
}
```
> El monto del aporte no fue mencionado → `incompleta`. El LLM no asume ningún valor por defecto.

**Frase 2 (correcto, con monto):** "Luz Marina me dio ochenta de ahorro y también pagó una cuota de su deuda"
```json
{
  "intencion": "registrar_combinado",
  "recibi_de": "Luz Marina",
  "aportes": [{"nombre": "Luz Marina", "monto": 80000}],
  "pagos": [{"nombre": "Luz Marina", "n_cuotas": 1, "abono_capital": 0}]
}
```

**Frase 3:** "Recibí a don Alberto, él pagó dos cuotas y además trajo el ahorro de su esposa Lucía por ochenta mil"
```json
{
  "intencion": "registrar_combinado",
  "recibi_de": "Alberto",
  "aportes": [{"nombre": "Lucía", "monto": 80000}],
  "pagos": [{"nombre": "Alberto", "n_cuotas": 2, "abono_capital": 0}]
}
```

---

### `incompleta`

**Frase:** "Recibí a Pedro"
```json
{
  "intencion": "incompleta",
  "intencion_detectada": "registrar_aporte",
  "campos_faltantes": ["monto"],
  "texto_original": "Recibí a Pedro"
}
```

---

### `desconocida`

**Frase:** "¿Cuándo es la próxima reunión?"
```json
{
  "intencion": "desconocida",
  "texto_original": "¿Cuándo es la próxima reunión?"
}
```

---

## Prompt del sistema para el LLM

El prompt de sistema que recibe el LLM debe:

1. Describir las intenciones disponibles con sus campos.
2. Dar ejemplos de frases → JSON (los de arriba).
3. Instruir explícitamente: **nunca calcules montos, saldos, intereses ni IDs**.
4. Instruir: si falta información, produce `incompleta` con `campos_faltantes`.
5. Incluir la fecha actual (para contexto temporal, no para cálculos).
6. **No incluir** la lista de socios ni datos financieros reales en el prompt (el contexto del bot no debe filtrar datos de la DB al modelo externo).

El prompt completo de producción está en `packages/bot/src/coop_bot/nlu/prompt_sistema.txt`.

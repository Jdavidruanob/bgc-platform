# 05 — Contrato de la API (`coop-api`)

> Especificación OpenAPI 3.1 en prosa + YAML parcial.
> El archivo `openapi.yaml` definitivo vive en `packages/contracts/src/coop_contracts/openapi.yaml`
> y se genera automáticamente desde el código FastAPI con `app.openapi()`.

---

## Convenciones globales

### Autenticación
Todos los endpoints (excepto `GET /health`) requieren:
```
Authorization: Bearer <token>
```
Token estático configurado en variable de entorno `API_SECRET_TOKEN`. Retorna `401` si falta o es inválido.

### Formato de error uniforme
```json
{
  "error": {
    "codigo": "SALDO_INSUFICIENTE",
    "mensaje": "El socio no tiene saldo suficiente para este retiro.",
    "detalle": null
  }
}
```
- `codigo`: slug en mayúsculas para que el bot pueda tomar decisiones por código, no por texto.
- `mensaje`: texto en español listo para mostrar al operador tal cual.
- `detalle`: información adicional estructurada (nullable).

### Códigos de error estándar

| Código HTTP | Cuándo |
|-------------|--------|
| 200 | Consulta exitosa |
| 201 | Operación de escritura exitosa |
| 400 | Request malformado (JSON inválido, campo faltante) |
| 401 | Token ausente o inválido |
| 404 | Recurso no encontrado (socio, letra) |
| 409 | Conflicto de idempotencia (ver §Idempotencia) |
| 422 | Error de validación de negocio (propagado desde `ValueError` de los servicios) |
| 500 | Error interno no anticipado |

### Idempotencia
Todos los endpoints de escritura (`POST`) requieren el header:
```
Idempotency-Key: <uuid-v4>
```
- Si el mismo `Idempotency-Key` llega por segunda vez, la API retorna `200` con el resultado original, sin re-ejecutar la operación.
- Si llega con payload diferente y misma key, retorna `409 Conflict`.
- Las keys se almacenan en la tabla `idempotency_keys` de Postgres con TTL de 24 horas.
- Ausencia del header en un POST retorna `400`.

---

## Endpoints de consulta

### `GET /health`
Sin autenticación. Para health checks del proveedor de hosting.

**Response 200:**
```json
{"status": "ok", "version": "0.1.0"}
```

---

### `GET /socios`
Búsqueda de socios por nombre (fuzzy).

**Query params:**
| Param | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `q` | string | Sí | Término de búsqueda (nombre o apellido) |
| `limit` | int | No (default: 10) | Máximo de resultados |

**Response 200:**
```json
{
  "socios": [
    {
      "id": 12,
      "nombres": "Pedro Antonio",
      "apellidos": "Gómez Ruiz",
      "nombre_completo": "Pedro Antonio Gómez Ruiz",
      "score": 0.95
    }
  ]
}
```

**Errores:**
- `400`: `q` no fue enviado o está vacío.

---

### `GET /socios/{socio_id}`
Datos completos de un socio.

**Response 200:**
```json
{
  "id": 12,
  "nombres": "Pedro Antonio",
  "apellidos": "Gómez Ruiz",
  "celular": "3001234567",
  "saldo": 320000,
  "creditos_activos": 1
}
```

**Errores:**
- `404`: `{"error": {"codigo": "SOCIO_NO_ENCONTRADO", "mensaje": "No existe un socio con ID 12.", "detalle": null}}`

---

### `GET /socios/{socio_id}/creditos`
Créditos activos de un socio.

**Response 200:**
```json
{
  "creditos": [
    {
      "letra_id": 450,
      "capital_original": 2000000,
      "interes_tasa": 0.02,
      "n_cuotas_total": 24,
      "fecha_inicio": "2025-03-01",
      "socios": ["Pedro Antonio Gómez Ruiz", "María López"]
    }
  ]
}
```

---

### `GET /creditos/{letra_id}/cuotas-pendientes`
Cuotas pendientes de pago de una letra.

**Response 200:**
```json
{
  "letra_id": 450,
  "deuda_total_actual": 1450000,
  "cuotas_pendientes": [
    {
      "nro_cuota": 5,
      "fecha_vencimiento": "2026-08-01",
      "valor_cuota": 85000,
      "interes_mes": 23400,
      "cuota_mensual": 108400,
      "mora_estimada": 0,
      "estado": "vigente"
    },
    {
      "nro_cuota": 6,
      "fecha_vencimiento": "2026-09-01",
      "valor_cuota": 85000,
      "interes_mes": 21700,
      "cuota_mensual": 106700,
      "mora_estimada": 0,
      "estado": "futuro"
    }
  ]
}
```

**Errores:**
- `404`: letra no existe.

---

### `GET /caja`
Estado actual de caja y fondo administrativo.

**Response 200:**
```json
{
  "saldo_en_caja": 5830000,
  "total_admin": 270000,
  "porcentaje_mora": 0.02
}
```

---

## Endpoints de operación

> Todos requieren `Idempotency-Key` en el header.

### `POST /operaciones/aportes`
Registra aportes de uno o varios socios.

**Request body:**
```json
{
  "recibi_de_id": 12,
  "aportes": [
    {"socio_id": 12, "monto": 80000},
    {"socio_id": 7, "monto": 80000}
  ]
}
```

**Notas:**
- `recibi_de_id`: ID del socio que entrega el dinero físicamente.
- `aportes`: lista de 1 a 6 aportes. El límite de 6 viene del máximo soportado por las plantillas de Excel del escritorio (para el bot es informativo).
- `monto`: entero positivo en pesos.
- **`count_cobrables` no se envía en el request.** La API lo calcula internamente consultando la lista de socios exentos de papelería (ver §Exención de papelería más abajo).

**Response 201:**
```json
{
  "recibo_id": 47,
  "fecha": "2026-07-18",
  "recibi_de": {"id": 12, "nombre_completo": "Pedro Antonio Gómez Ruiz"},
  "aportes": [
    {
      "socio_id": 12,
      "nombre_completo": "Pedro Antonio Gómez Ruiz",
      "monto": 80000,
      "saldo_anterior": 320000,
      "saldo_nuevo": 400000,
      "cobro_papeleria": false
    },
    {
      "socio_id": 7,
      "nombre_completo": "María López",
      "monto": 80000,
      "saldo_anterior": 150000,
      "saldo_nuevo": 230000,
      "cobro_papeleria": true
    }
  ],
  "papeleria_cobrada": 3000,
  "saldo_caja_nuevo": 5990000
}
```

**§ Exención de papelería**

La papelería ($3.000 por aporte) se cobra a cada socio **excepto** a los que estén en la lista de exentos. Esta lista vive en `coop-core` como constante y es consultada por la API antes de llamar al servicio.

Implementación en `coop-core`:
```python
# packages/core/src/coop_core/config/papeleria.py

# IDs de socios exentos de cobro de papelería.
# Fase inicial: hardcodeados. Fase futura: leer de tabla config en DB.
SOCIOS_EXENTOS_PAPELERIA: frozenset[int] = frozenset({
    # Ejemplo: ID del tesorero/operador
    # Añadir IDs reales antes del primer deploy
})

def es_cobrable(socio_id: int) -> bool:
    return socio_id not in SOCIOS_EXENTOS_PAPELERIA

def count_cobrables(socio_ids: list[int]) -> int:
    return sum(1 for sid in socio_ids if es_cobrable(sid))
```

La API llama a `count_cobrables([a.socio_id for a in aportes])` antes de invocar `AporteService.register`. El bot no necesita conocer esta lógica.
```

**Errores:**
- `400`: `aportes` vacío, monto ≤ 0, `recibi_de_id` inválido.
- `404`: algún `socio_id` no existe.
- `422`: error de negocio del servicio.

---

### `POST /operaciones/retiros`
Registra un retiro.

**Request body:**
```json
{
  "socio_id": 7,
  "monto": 200000
}
```

**Response 201:**
```json
{
  "recibo_id": 48,
  "fecha": "2026-07-18",
  "socio": {"id": 7, "nombre_completo": "María López"},
  "monto_retirado": 200000,
  "saldo_anterior": 230000,
  "saldo_nuevo": 30000,
  "saldo_caja_nuevo": 5790000
}
```

**Errores:**
- `422`: `{"error": {"codigo": "SALDO_INSUFICIENTE", "mensaje": "El socio no tiene saldo suficiente para este retiro.", "detalle": null}}`

---

### `POST /operaciones/pagos`
Registra pagos de crédito.

**Request body:**
```json
{
  "recibi_de_id": 12,
  "pagos": [
    {
      "socio_id": 12,
      "letra_id": 450,
      "n_cuotas": 2,
      "abono_capital": 0
    }
  ]
}
```

**Notas:**
- `n_cuotas` y `abono_capital` son mutuamente excluyentes (exactamente uno debe ser > 0).
- Si `abono_capital` > 0, el backend aplica el modo cascada (paga cuotas vencidas primero, luego abona capital).

**Response 201:**
```json
{
  "recibo_id": 49,
  "fecha": "2026-07-18",
  "recibi_de": {"id": 12, "nombre_completo": "Pedro Antonio Gómez Ruiz"},
  "pagos": [
    {
      "socio_id": 12,
      "nombre_completo": "Pedro Antonio Gómez Ruiz",
      "letra_id": 450,
      "cuotas_pagadas": [5, 6],
      "capital_pagado": 170000,
      "intereses_pagados": 45100,
      "mora_pagada": 0,
      "total_pagado": 215100,
      "saldo_capital_antes": 1450000,
      "saldo_capital_despues": 1280000
    }
  ],
  "saldo_caja_nuevo": 5835000
}
```

**Errores:**
- `422`: cuotas insuficientes, abono insuficiente, modo dual activado.

---

### `POST /operaciones/combinados`
Registra aportes y pagos en un solo recibo.

**Request body:**
```json
{
  "recibi_de_id": 12,
  "aportes": [
    {"socio_id": 12, "monto": 80000}
  ],
  "pagos": [
    {"socio_id": 12, "letra_id": 450, "n_cuotas": 1, "abono_capital": 0}
  ]
}
```

**Response 201:** combinación de los datos de aportes y pagos en un solo objeto, con `recibo_id` único.

---

## Errores de negocio documentados (código → mensaje)

| Código | Mensaje español | Origen |
|--------|-----------------|--------|
| `SALDO_INSUFICIENTE` | "El socio no tiene saldo suficiente para este retiro." | `RetiroService` |
| `CUOTAS_INSUFICIENTES` | "No hay suficientes cuotas pendientes en la letra {letra} para {nombre}." | `PagoService` |
| `ABONO_INSUFICIENTE` | "Abono insuficiente para {nombre} (Letra {letra}): no cubre la primera cuota vencida." | `PagoService` |
| `ABONO_INCOMPLETO` | "Abono incompleto en letra {letra} para {nombre}. El monto no alcanza para cubrir las cuotas vencidas parcialmente." | `PagoService` |
| `MODO_DUAL_PAGO` | "Seleccione solo una opción: cuotas O abono." | `PagoService` |
| `SIN_OPERACIONES` | "No hay operaciones válidas para registrar." | `PagoService`, `CombinadoService` |
| `SOCIO_NO_ENCONTRADO` | "No existe un socio con ID {id}." | `coop-api` |
| `LETRA_NO_ENCONTRADA` | "No existe un crédito con letra {letra}." | `coop-api` |
| `IDEMPOTENCY_CONFLICT` | "La clave de idempotencia ya fue usada con un payload diferente." | `coop-api` |

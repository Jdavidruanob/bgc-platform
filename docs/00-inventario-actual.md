# 00 — Inventario actual del código existente

> Generado leyendo directamente `BGC-software/` el 2026-07-18.
> Todo lo que aquí aparece está respaldado por código leído, no por suposiciones.

---

## 1. Mapa de archivos y responsabilidades

```
BGC-software/
├── app.py                          Punto de entrada. Wiring: crea DBManager, instancia
│                                   todos los servicios, monta las vistas.
├── config.py                       ⚠️ ARCHIVO MIXTO (ver §4). Contiene:
│                                   - Rutas de sistema de archivos (DB_PATH, ASSETS_DIR,
│                                     RECIBOS_OUTPUT_DIR, LIQUIDACIONES_OUTPUT_DIR)
│                                   - Funciones de fecha con modo "viaje en el tiempo"
│                                     (get_hoy, get_hoy_str, set_fecha_simulada)
│                                   - Funciones de formato (format_miles_colombian_int,
│                                     format_full_name_for_excel)
│                                   - Constantes de color UI
│                                   - Funciones Qt (load_styles, load_svg_icon)
│                                   - Imports de PySide6 al nivel del módulo
├── db/
│   ├── connection.py               DBConnection: wraper sobre sqlite3.connect().
│   │                               Expone .conn (sqlite3.Connection) y .row_factory.
│   ├── schema.py                   SchemaManager: CREATE TABLE IF NOT EXISTS para todas
│   │                               las tablas. También gestiona sqlite_sequence.
│   ├── migration.py                MigrationService: migración anual de saldos entre
│   │                               archivos DB de distintos años fiscales.
│   ├── db_manager.py               Fachada. Instancia todos los repos, delega. Las vistas
│   │                               acceden a la DB a través de esta fachada.
│   └── repositories/
│       ├── socios_repo.py          CRUD socios. Retorna sqlite3.Row o list[dict].
│       ├── creditos_repo.py        CRUD créditos + cálculo de amortización dentro del repo.
│       ├── liquidaciones_repo.py   Cuotas pendientes, deuda actual, recálculo post-abono.
│       ├── recibos_repo.py         Solo create_aporte (usado por versión antigua, no
│       │                           por los servicios actuales).
│       ├── auxiliar_repo.py        Libro auxiliar contable. delete() tiene lógica de
│       │                           negocio (recalcula saldos corridos + actualiza config).
│       └── config_repo.py          Tabla clave-valor. get/set/get_int.
├── services/
│   ├── amortization.py             Funciones matemáticas puras: calculate_mora,
│   │                               round_installments, build_amortization_schedule.
│   ├── aporte_service.py           Registra aportes de uno o varios socios.
│   ├── retiro_service.py           Registra retiro de un socio.
│   ├── credito_service.py          Crea crédito nuevo + tabla de amortización.
│   ├── pago_service.py             Pago de cuotas en dos modos: manual y abono-cascada.
│   ├── combinado_service.py        Aporte + pago en un solo recibo. ⚠️ Duplica código
│   │                               de PagoService (_prepare_cuotas, _prepare_abono,
│   │                               _execute_op son copias exactas).
│   └── caja_service.py             Consulta y ajuste de saldo en caja y fondo admin.
├── utils/
│   ├── recibo_generator_aporte.py  Genera Excel de recibo de aportes con openpyxl.
│   ├── recibo_generator_retiro.py  Genera Excel de recibo de retiro.
│   ├── recibo_generator_pago.py    Genera Excel de recibo de pagos.
│   ├── recibo_generator_combinado.py Genera Excel de recibo combinado.
│   ├── credit_liquidation_generator.py Genera Excel de tabla de amortización.
│   └── message_boxes.py            Cuadros de diálogo Qt. Solo UI.
└── views/                          Vistas PySide6. No las inspeccioné en detalle
    │                               (fuera del alcance del inventario de servicios).
    ├── main_window.py
    ├── home_page.py
    ├── assistant_page.py
    ├── members_page.py
    └── data_page.py
```

---

## 2. Firmas exactas de métodos públicos por servicio

### `AporteService` (`services/aporte_service.py`)

```python
class AporteService:
    def __init__(self, db: DBConnection, config: ConfigRepository, auxiliar: AuxiliarRepository)

    def register(
        self,
        recibi_de_id: int,          # ID del socio que entrega el dinero
        recibi_data: dict,          # {"nombres": str, "apellidos": str}
        aportes: list,              # list[tuple[dict, int]] → (socio_data, monto)
                                    # socio_data: {"id": int, "nombres": str,
                                    #              "apellidos": str, "saldo": int}
        count_cobrables: int,       # nro de aportes con papelería cobrable ($3.000 c/u)
    ) -> tuple[int, str]:           # (recibo_id, excel_path)
```

Lanza: no lanza `ValueError` explícito (delega la validación a la vista).

---

### `RetiroService` (`services/retiro_service.py`)

```python
class RetiroService:
    def __init__(self, db: DBConnection, config: ConfigRepository, auxiliar: AuxiliarRepository)

    def register(
        self,
        socio_id: int,
        socio_data: dict,           # {"nombres": str, "apellidos": str, "saldo": int}
        monto: int,
    ) -> tuple[int, str, int]:      # (recibo_id, excel_path, nuevo_saldo_caja)
```

Lanza: `ValueError("El socio no tiene saldo suficiente para este retiro.")` si `monto > socio_data["saldo"]`.

---

### `CreditoService` (`services/credito_service.py`)

```python
class CreditoService:
    def __init__(self, db: DBConnection, creditos: CreditosRepository,
                 auxiliar: AuxiliarRepository, config: ConfigRepository)

    def create(
        self,
        socio_ids: list,            # list[int]
        capital: int,
        interes_tasa: float,        # p.ej. 0.02 (2 %)
        n_cuotas: int,
        socios_data: list,          # list[dict] → [{"nombres": str, "apellidos": str}]
    ) -> tuple[int, str]:           # (letra_id, excel_path)
```

Lanza: excepciones de `CreditosRepository.register_complete` (reraised).

---

### `PagoService` (`services/pago_service.py`)

```python
class PagoService:
    def __init__(self, db: DBConnection, liquidaciones: LiquidacionesRepository,
                 auxiliar: AuxiliarRepository, config: ConfigRepository)

    def register(
        self,
        recibi_de_id: int,
        recibi_data: dict,          # {"nombres": str, "apellidos": str}
        pagos_input: list,          # list[dict]:
                                    # {
                                    #   "socio_data": {"id": int, "nombres": str, "apellidos": str},
                                    #   "letra_id": int,
                                    #   "n_cuotas": int,      # modo manual (excluyente)
                                    #   "abono_capital": int, # modo cascada (excluyente)
                                    # }
    ) -> tuple[int, str, dict]:     # (recibo_id, excel_path, reporte_global)
                                    # reporte_global: {nombre_socio: list[str]}
```

Lanza:
- `ValueError("No hay operaciones válidas para registrar.")` si `pagos_input` está vacío.
- `ValueError(f"En el pago de {nombre} (Letra {letra_id}) seleccione solo una opción: cuotas O abono.")` si ambos modos activos.
- `ValueError(f"No hay suficientes cuotas pendientes en la letra {letra_id} para {nombre}.")`.
- `ValueError(f"Abono insuficiente para {nombre} (Letra {letra_id}): no cubre la primera cuota vencida.")`.
- `ValueError(f"Abono incompleto en letra {letra_id} para {nombre}. El monto no alcanza para cubrir las cuotas vencidas parcialmente.")`.

---

### `CombinadoService` (`services/combinado_service.py`)

```python
class CombinadoService:
    def __init__(self, db: DBConnection, liquidaciones: LiquidacionesRepository,
                 auxiliar: AuxiliarRepository, config: ConfigRepository)

    def register(
        self,
        recibi_de_id: int,
        recibi_data: dict,          # {"nombres": str, "apellidos": str}
        aportes_input: list,        # list[dict]: {"socio_data": dict, "monto": int}
        pagos_input: list,          # igual que PagoService.register.pagos_input
        count_cobrables: int,
    ) -> tuple[int, str, dict]:     # (recibo_id, excel_path, reporte_global)
```

Lanza: los mismos `ValueError` que `PagoService.register` más:
- `ValueError("No hay operaciones válidas para registrar.")` si ambas listas vacías.

---

### `CajaService` (`services/caja_service.py`)

```python
class CajaService:
    def __init__(self, config: ConfigRepository, auxiliar: AuxiliarRepository)

    def get_saldo_caja(self) -> int
    def get_total_admin(self) -> int
    def get_porcentaje_mora(self) -> float

    def adjust_caja(
        self,
        monto_ajuste: int,          # puede ser negativo
        motivo: str,
        nuevo_saldo: int,
    ) -> None

    def set_admin_config(
        self,
        new_papeleria: int,
        new_mora: float,
    ) -> None
```

No lanza `ValueError`.

---

### `amortization.py` (funciones puras, sin clase)

```python
def calculate_mora(
    fecha_venc_str: str,            # "YYYY-MM-DD"
    hoy: date,
    valor_cuota: int,
    tasa_mora: float,
) -> int                            # 0 si dentro del mes de gracia

def round_installments(
    capital: int,
    n_cuotas: int,
) -> tuple[int, int]                # (cuota_base, cuota_final)

def build_amortization_schedule(
    letra_id: int,
    capital: int,
    interes: float,
    n_cuotas: int,
    fecha_inicio: date,
) -> list[tuple]                    # 7-tuplas listas para INSERT INTO liquidaciones
```

---

## 3. Acoplamientos a SQLite que definen el esfuerzo de migración

### 3.1 SQL con dialectos o comportamientos SQLite-específicos

| Archivo | Línea aprox. | Patrón problemático |
|---------|-------------|---------------------|
| `db/schema.py` | 29 | `INTEGER PRIMARY KEY AUTOINCREMENT` — en Postgres es `SERIAL` o `GENERATED ALWAYS AS IDENTITY` |
| `db/schema.py` | 132 | `sqlite_sequence` — tabla interna de SQLite, no existe en Postgres |
| `db/schema.py` | 117 | `INSERT OR IGNORE INTO config` — es `INSERT ... ON CONFLICT DO NOTHING` en Postgres |
| `db/repositories/config_repo.py` | 26 | `INSERT ... ON CONFLICT(key) DO UPDATE SET value = excluded.value` — UPSERT: compatible con Postgres 9.5+, sin cambio |
| `db/repositories/auxiliar_repo.py` | 79 | `INSERT INTO config ... ON CONFLICT(key) DO UPDATE` — ídem |
| `db/repositories/creditos_repo.py` | 199 | `UPDATE liquidaciones SET fecha_pago = DATE('now')` en `PagoService` — `DATE('now')` es SQLite; Postgres usa `CURRENT_DATE` |
| `services/pago_service.py` | 199, 226 | `DATE('now')` en SQL inline — mismo problema |
| `services/combinado_service.py` | 236, 261 | `DATE('now')` en SQL inline |
| `db/connection.py` | 11 | `sqlite3.connect()` + `sqlite3.Row` — todo esto cambia por `psycopg2` o `asyncpg` |

### 3.2 Patrón de transacciones

Los servicios manejan transacciones accediendo **directamente** a `self._db.conn`:

```python
cursor = self._db.conn.cursor()
# ... ejecuta SQL ...
self._db.conn.commit()
# ... en except:
self._db.conn.rollback()
```

En SQLite esto funciona porque hay un solo proceso y una sola conexión. Al migrar a Postgres con un pool de conexiones, este patrón necesita adaptarse: la conexión debe ser obtenida del pool para cada request, no guardada como atributo de instancia del servicio.

**Riesgo alto**: los servicios guardan `self._db` (el objeto `DBConnection`) como atributo. En un contexto web con múltiples requests concurrentes, esto produce race conditions. La solución es pasar la conexión/sesión como parámetro de la operación, no como dependencia de instancia.

### 3.3 Tipos de datos

| Campo | Tipo SQLite | Observación |
|-------|-------------|-------------|
| `socios.saldo` | `INTEGER` | ✅ Seguro |
| `creditos.capital` | `INTEGER` | ✅ Seguro |
| `creditos.interes` | `REAL` | ⚠️ La tasa de interés se guarda como float. En Postgres usar `NUMERIC(5,4)` para evitar imprecisiones de `REAL` |
| `liquidaciones.valor_cuota` | `INTEGER` | ✅ Seguro |
| `liquidaciones.interes_mes` | `INTEGER` | ✅ Seguro |
| `config.value` | `TEXT` | ⚠️ Todos los valores financieros se guardan como texto (`"150000"`). `ConfigRepository.get_int()` los parsea. Funciona, pero es frágil |
| `auxiliar.monto` | `INTEGER` | ✅ Seguro |
| Fechas | `TEXT "YYYY-MM-DD"` / `TIMESTAMP` | ⚠️ SQLite no tiene tipo DATE nativo. El código parsea fechas con `datetime.strptime(..., "%Y-%m-%d")`. En Postgres usar `DATE` real |

### 3.4 `CreditosRepository.register_complete` tiene lógica de negocio

Este método en el repositorio:
1. Calcula la tabla de amortización (lógica idéntica a `build_amortization_schedule` en `amortization.py`).
2. Lee `config.saldo_en_caja` directamente dentro de la transacción del crédito.
3. Retorna el nuevo saldo sin persistirlo (lo persiste `CreditoService`).

Es decir, **hay duplicación de lógica** entre `creditos_repo.register_complete` y `amortization.build_amortization_schedule`. Al migrar a `coop-core`, se debe consolidar en uno solo.

---

## 4. Acoplamientos al sistema de archivos (generación de Excel)

### 4.1 Dependencias de rutas en `config.py`

Los generadores de Excel importan estas constantes desde `config.py`:

```python
from config import (
    ASSETS_DIR,             # Directorio de assets (contiene plantillas .xlsx)
    RECIBOS_OUTPUT_DIR,     # Donde se guardan los recibos generados
    LIQUIDACIONES_OUTPUT_DIR,
    get_hoy,                # Para el nombre del archivo y la celda de fecha
    format_miles_colombian_int,
    format_full_name_for_excel,
)
```

`ASSETS_DIR` apunta a `_MEIPASS` cuando el ejecutable está empaquetado con PyInstaller, o al directorio del script en desarrollo. Las plantillas `.xlsx` están en `ASSETS_DIR/templates/recibo_template_aporte/`.

### 4.2 Plantillas Excel requeridas

| Generador | Plantillas necesarias |
|-----------|----------------------|
| `recibo_generator_aporte.py` | `recibo_template_aporte{1..6}.xlsx` (una por cantidad de aportes) |
| `recibo_generator_retiro.py` | plantilla de retiro (a verificar) |
| `recibo_generator_pago.py` | plantilla de pagos |
| `recibo_generator_combinado.py` | plantilla combinada |
| `credit_liquidation_generator.py` | plantilla de tabla de amortización |

### 4.3 Implicación para `coop-core`

Los generadores de Excel **no son lógica de negocio** — son presentación. El equivalente en el bot será un PDF. Al extraer `coop-core`, los servicios deben dejar de retornar `excel_path` y en cambio retornar los datos estructurados necesarios para generar el comprobante. El generador de Excel queda en `packages/desktop/`; el generador de PDF queda en `packages/bot/`.

---

## 5. El problema crítico: `config.py` importa PySide6

Esta es la desviación más importante respecto a lo que describes en el prompt.

**Lo que dijiste:** "Los servicios en `services/*.py` son clases Python puras... no importan Qt en ninguna parte."

**Lo que encontré:** Es correcto que los archivos `services/*.py` no importan Qt directamente. Sin embargo, todos los servicios importan `from config import get_hoy_str` (o `get_hoy`), y `config.py` tiene en su primera línea:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, ...
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
```

Esto significa que **instalar `coop-core` requeriría instalar PySide6** como dependencia transitiva, a menos que se separe `config.py`. Esto es un blocker para el bot y la API.

Los generadores de Excel también importan de `config.py`.

**Solución al extraer:** Crear en `coop-core` un módulo `core/utils/` con solo las funciones puras que los servicios necesitan:
- `get_hoy() / get_hoy_str()` (con el modo simulado para tests)
- `format_miles_colombian_int()`
- `format_full_name_for_excel()`

Y dejar en `packages/desktop/` todo lo que toca Qt (colores, `load_styles`, `load_svg_icon`).

---

## 6. Riesgos concretos para la extracción a paquete

### Riesgo 1 — `config.py` contamina con PySide6 (BLOCKER)
**Severidad:** Alta. Sin resolver esto, `coop-core` no se puede instalar en un entorno sin Qt.
**Acción:** Separar `config.py` en tres artefactos:
- `core/utils/fecha.py` — `get_hoy`, `get_hoy_str`, `set_fecha_simulada`
- `core/utils/formato.py` — `format_miles_colombian_int`, `format_full_name_for_excel`
- `desktop/config.py` — rutas, colores, funciones Qt (queda en el escritorio)

### Riesgo 2 — Los servicios abren cursores directamente
**Severidad:** Alta para concurrencia. Los servicios hacen `self._db.conn.cursor()` en métodos auxiliares (`_prepare_cuotas` abre un cursor mientras hay otro abierto en la misma transacción). En SQLite esto es inocuo. En Postgres con un pool, puede causar que se use una conexión diferente para el cursor auxiliar.
**Acción:** Al migrar, hacer que cada método de servicio reciba la conexión/sesión como parámetro local, no como atributo de instancia.

### Riesgo 3 — `DATE('now')` hardcodeado en SQL
**Severidad:** Media. Dos consecuencias: (a) no funciona en Postgres; (b) rompe el modo "viaje en el tiempo" (`get_hoy()` tiene un override pero el SQL siempre usa la fecha real del servidor).
**Acción:** Reemplazar `DATE('now')` por el parámetro de fecha ya calculado en Python (`fecha = get_hoy_str()`), que ya está disponible en todos los métodos de los servicios.

### Riesgo 4 — Lógica de amortización duplicada en `CreditosRepository`
**Severidad:** Media. `register_complete` recalcula la amortización con código diferente al de `amortization.build_amortization_schedule`. Si hay un bug en uno, el otro puede no tenerlo.
**Acción:** Eliminar el cálculo de `register_complete` y delegar a `build_amortization_schedule`.

### Riesgo 5 — `AuxiliarRepository.delete` tiene lógica de negocio
**Severidad:** Baja-media. Recalcula saldos corridos y actualiza `config`. Esto mezcla persistencia con lógica. En el contexto actual no es problema, pero al añadir API/bot podría desincronizarse.
**Acción:** Mover la lógica de recálculo a un servicio o dejar documentado que este método es "operación compuesta".

### Riesgo 6 — Los servicios retornan `excel_path`
**Severidad:** Media. Los tests de servicios en `coop-core` necesitarán un sistema de archivos con las plantillas, o mockear los generadores. Al separar, los servicios deben devolver datos estructurados y el generador de comprobante queda fuera.
**Acción:** Refactorizar la firma de retorno: los servicios retornan `dict` con los datos del comprobante; el caller (vista de escritorio o endpoint de API) decide qué hacer con esos datos (generar Excel, generar PDF, responder JSON).

### Riesgo 7 — Migración anual de año fiscal (lógica en `db/migration.py`)
**Severidad:** Media. La app actualmente usa una DB por año fiscal. Al migrar a Postgres en la nube, esta lógica debe revisarse: o se lleva histórico en una sola DB (recomendado) o se mantiene el ciclo anual.
**Acción:** Decidir antes de migrar si el histórico convive en una sola base. Ver ADR correspondiente.

### Riesgo 8 — `CombinadoService` duplica `PagoService`
**Severidad:** Baja (no bloquea extracción, pero es deuda técnica). Los tres métodos privados son copias exactas.
**Acción:** En `coop-core`, hacer que `CombinadoService` use `PagoService` internamente, o extraer los helpers a un módulo compartido.

### Riesgo 9 — `config.value` almacena enteros como texto
**Severidad:** Baja. `saldo_en_caja`, `total_admin`, `porcentaje_mora` son strings en la tabla `config`. Si un bug deja un string inválido, `get_int()` retorna 0 silenciosamente.
**Acción:** Al migrar a Postgres, reemplazar la tabla `config` de clave-valor por columnas tipadas o usar tipos correctos en JSON.

---

## 7. Verificación de la política de dinero en enteros

Hallazgos del análisis del código:

| Aspecto | Estado |
|---------|--------|
| Saldos de socios (`socios.saldo`) | ✅ `INTEGER` en DB, `int` en código |
| Montos en `detalle_recibo` | ✅ `INTEGER NOT NULL` |
| Montos en `auxiliar` | ✅ `INTEGER NOT NULL` |
| Cuotas de amortización (capital, interés) | ✅ `int(...)` explícito en todos los cálculos |
| `calculate_mora` | ✅ `int(valor_cuota * tasa_mora)` — trunca, no redondea |
| Tasa de interés (`creditos.interes`) | ⚠️ `REAL` en DB, `float` en código — es una tasa, no un monto, pero podría acumular errores si se lee/escribe muchas veces |
| `config.value` (saldo_en_caja, total_admin) | ⚠️ `TEXT` en DB, parseado con `int()` — funciona pero no es tipado |
| Ningún servicio usa `float` para montos | ✅ Confirmado |

**Conclusión:** El código existente respeta la política "enteros para dinero" en los montos. La excepción es la tasa de interés, que es un porcentaje (no un monto) y usar `float` es aceptable. Al migrar a Postgres, cambiar `REAL` a `NUMERIC(5,4)` para la tasa sería más robusto.

---

## 8. Resumen ejecutivo para decisiones de arquitectura

| Pregunta | Respuesta basada en código |
|----------|---------------------------|
| ¿Los servicios son libres de Qt? | Casi: no importan Qt directamente, pero importan `config.py` que sí lo hace |
| ¿El patrón de repositorios está limpio? | En su mayoría sí, con dos excepciones: `creditos_repo.register_complete` tiene lógica de negocio y `auxiliar_repo.delete` tiene efectos secundarios de negocio |
| ¿Se puede extraer `coop-core` sin reescribir servicios? | Sí, con tres cambios obligatorios: (1) separar `config.py`, (2) reemplazar `DATE('now')` por parámetro Python, (3) separar los retornos de excel_path |
| ¿La gestión de transacciones es compatible con Postgres? | No directamente: los servicios guardan `self._db.conn` como atributo de instancia. En un contexto web multi-request esto es un problema |
| ¿El código maneja dinero con enteros? | Sí, los montos son enteros. La tasa de interés usa float, lo cual es aceptable |
| ¿Hay lógica duplicada? | Sí: `CombinadoService` duplica `PagoService`. `creditos_repo.register_complete` duplica `amortization.build_amortization_schedule` |

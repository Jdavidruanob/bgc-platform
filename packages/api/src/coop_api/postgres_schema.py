"""DDL nativo de PostgreSQL para inicializar la base de datos en staging/producción.

El schema de tests usa SQLite con `INTEGER PRIMARY KEY` (que auto-incrementa).
Postgres necesita `GENERATED ALWAYS AS IDENTITY` para el mismo comportamiento.
Este archivo solo se ejecuta en el lifespan de la API real; nunca en tests.
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS socios (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cc          TEXT,
    nombres     TEXT NOT NULL,
    apellidos   TEXT NOT NULL,
    saldo       INTEGER DEFAULT 0,
    celular     TEXT,
    photo_path  TEXT,
    whatsapp_e164       TEXT,
    optin_whatsapp_fecha TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS creditos (
    letra       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    capital     INTEGER NOT NULL,
    interes     REAL NOT NULL,
    no_cuotas   INTEGER NOT NULL,
    fecha_inicio TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS socio_credito (
    socio_id        INTEGER NOT NULL REFERENCES socios(id),
    credito_letra   INTEGER NOT NULL REFERENCES creditos(letra),
    PRIMARY KEY (socio_id, credito_letra)
);

CREATE TABLE IF NOT EXISTS liquidaciones (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    credito_letra       INTEGER NOT NULL REFERENCES creditos(letra),
    nro_cuota           INTEGER NOT NULL,
    fecha_vencimiento   TEXT NOT NULL,
    valor_cuota         INTEGER NOT NULL,
    interes_mes         INTEGER NOT NULL,
    cuota_mensual       INTEGER NOT NULL,
    saldo_capital       INTEGER NOT NULL,
    fecha_pago          TEXT,
    interes_mora        INTEGER DEFAULT 0,
    mora_aplicada       INTEGER DEFAULT 0,
    notif_prev_enviada  INTEGER DEFAULT 0,
    notif_venc_enviada  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recibos (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    socio_id    INTEGER NOT NULL REFERENCES socios(id),
    fecha       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS detalle_recibo (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recibo_id       INTEGER NOT NULL REFERENCES recibos(id),
    tipo_operacion  TEXT NOT NULL,
    socio_id        INTEGER NOT NULL REFERENCES socios(id),
    credito_letra   INTEGER,
    nro_cuota       INTEGER,
    monto           INTEGER NOT NULL,
    abono_mora      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auxiliar (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha       TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    socio       TEXT NOT NULL,
    recibo      INTEGER,
    monto       INTEGER NOT NULL,
    saldo       INTEGER NOT NULL,
    cuota       INTEGER,
    id_credito  TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE TABLE IF NOT EXISTS notificaciones_whatsapp (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    socio_id            INTEGER NOT NULL REFERENCES socios(id),
    numero_e164         TEXT NOT NULL,
    texto               TEXT NOT NULL,
    estado              TEXT NOT NULL DEFAULT 'pendiente',
    intentos            INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_intento_at   TIMESTAMP,
    error               TEXT
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key             TEXT PRIMARY KEY,
    endpoint        TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    response_json   TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_message_id TEXT,
    chat_id             TEXT NOT NULL,
    audio_url           TEXT,
    transcripcion       TEXT,
    intencion_json      TEXT,
    operacion_tipo      TEXT,
    operacion_id        INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CONFIG_DEFAULTS = {
    "saldo_en_caja": "0",
    "total_admin": "0",
    "porcentaje_mora": "0.02",
}

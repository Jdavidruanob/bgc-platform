"""
DDL compatible con PostgreSQL y SQLite 3.35+.
No usa DATE('now'), sqlite_sequence ni INSERT OR IGNORE.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS socios (
    id INTEGER PRIMARY KEY,
    cc TEXT,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    saldo INTEGER DEFAULT 0,
    celular TEXT,
    photo_path TEXT,
    whatsapp_e164 TEXT,
    optin_whatsapp_fecha TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS creditos (
    letra INTEGER PRIMARY KEY,
    capital INTEGER NOT NULL,
    interes REAL NOT NULL,
    no_cuotas INTEGER NOT NULL,
    fecha_inicio TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS socio_credito (
    socio_id INTEGER NOT NULL,
    credito_letra INTEGER NOT NULL,
    PRIMARY KEY (socio_id, credito_letra),
    FOREIGN KEY (socio_id) REFERENCES socios(id),
    FOREIGN KEY (credito_letra) REFERENCES creditos(letra)
);

CREATE TABLE IF NOT EXISTS liquidaciones (
    id INTEGER PRIMARY KEY,
    credito_letra INTEGER NOT NULL,
    nro_cuota INTEGER NOT NULL,
    fecha_vencimiento TEXT NOT NULL,
    valor_cuota INTEGER NOT NULL,
    interes_mes INTEGER NOT NULL,
    cuota_mensual INTEGER NOT NULL,
    saldo_capital INTEGER NOT NULL,
    fecha_pago TEXT,
    interes_mora INTEGER DEFAULT 0,
    mora_aplicada INTEGER DEFAULT 0,
    notif_prev_enviada INTEGER DEFAULT 0,
    notif_venc_enviada INTEGER DEFAULT 0,
    FOREIGN KEY (credito_letra) REFERENCES creditos(letra)
);

CREATE TABLE IF NOT EXISTS recibos (
    id INTEGER PRIMARY KEY,
    socio_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (socio_id) REFERENCES socios(id)
);

CREATE TABLE IF NOT EXISTS detalle_recibo (
    id INTEGER PRIMARY KEY,
    recibo_id INTEGER NOT NULL,
    tipo_operacion TEXT NOT NULL,
    socio_id INTEGER NOT NULL,
    credito_letra INTEGER,
    nro_cuota INTEGER,
    monto INTEGER NOT NULL,
    abono_mora INTEGER DEFAULT 0,
    FOREIGN KEY (recibo_id) REFERENCES recibos(id),
    FOREIGN KEY (socio_id) REFERENCES socios(id)
);

CREATE TABLE IF NOT EXISTS auxiliar (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,
    socio TEXT NOT NULL,
    recibo INTEGER,
    monto INTEGER NOT NULL,
    saldo INTEGER NOT NULL,
    cuota INTEGER,
    id_credito TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS notificaciones_whatsapp (
    id INTEGER PRIMARY KEY,
    socio_id INTEGER NOT NULL,
    numero_e164 TEXT NOT NULL,
    texto TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    intentos INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_intento_at TIMESTAMP,
    error TEXT,
    FOREIGN KEY (socio_id) REFERENCES socios(id)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    telegram_message_id TEXT,
    chat_id TEXT NOT NULL,
    audio_url TEXT,
    transcripcion TEXT,
    intencion_json TEXT,
    operacion_tipo TEXT,
    operacion_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recibos_archivos (
    recibo_id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL,
    xlsx_bytes BLOB NOT NULL,
    pdf_bytes BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recibo_id) REFERENCES recibos(id)
);
"""

CONFIG_DEFAULTS = {
    "saldo_en_caja": "0",
    "total_admin": "0",
    "porcentaje_mora": "0.02",
}

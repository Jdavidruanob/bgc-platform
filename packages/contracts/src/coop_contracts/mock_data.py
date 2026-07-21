"""Datos ficticios para el mock server. Incluye un par de homónimos para testear R-05."""

from __future__ import annotations

import copy

SOCIOS_INICIALES: list[dict] = [
    {
        "id": 1,
        "nombres": "Pedro Antonio",
        "apellidos": "Gómez Ruiz",
        "celular": "3001234567",
        "whatsapp_e164": "+573001234567",
        "saldo": 320000,
        "creditos_activos": 1,
    },
    {
        "id": 2,
        "nombres": "Pedro Luis",
        "apellidos": "Gómez Castro",
        "celular": "3009876543",
        "whatsapp_e164": "+573009876543",
        "saldo": 150000,
        "creditos_activos": 0,
    },
    {
        "id": 3,
        "nombres": "María",
        "apellidos": "López Herrera",
        "celular": "3112223344",
        "whatsapp_e164": "+573112223344",
        "saldo": 250000,
        "creditos_activos": 0,
    },
    {
        "id": 4,
        "nombres": "Carmenza",
        "apellidos": "Suárez Peña",
        "celular": "3124445566",
        "whatsapp_e164": "+573124445566",
        "saldo": 180000,
        "creditos_activos": 0,
    },
    {
        "id": 5,
        "nombres": "Hernando",
        "apellidos": "Ruiz Vargas",
        "celular": "3201112233",
        "whatsapp_e164": "+573201112233",
        "saldo": 500000,
        "creditos_activos": 1,
    },
]

CREDITOS_INICIALES: list[dict] = [
    {
        "letra_id": 450,
        "socio_ids": [1],
        "capital_original": 2000000,
        "saldo_capital": 1450000,
        "interes_tasa": 0.02,
        "n_cuotas_total": 24,
        "fecha_inicio": "2025-03-01",
        "socios_nombres": ["Pedro Antonio Gómez Ruiz"],
        "cuotas_pendientes": [
            {
                "nro_cuota": 5,
                "fecha_vencimiento": "2026-08-01",
                "valor_cuota": 85000,
                "interes_mes": 23400,
                "cuota_mensual": 108400,
                "mora_estimada": 0,
                "estado": "vigente",
            },
            {
                "nro_cuota": 6,
                "fecha_vencimiento": "2026-09-01",
                "valor_cuota": 85000,
                "interes_mes": 21700,
                "cuota_mensual": 106700,
                "mora_estimada": 0,
                "estado": "futuro",
            },
        ],
    },
    {
        "letra_id": 451,
        "socio_ids": [5],
        "capital_original": 1500000,
        "saldo_capital": 900000,
        "interes_tasa": 0.02,
        "n_cuotas_total": 10,
        "fecha_inicio": "2025-10-01",
        "socios_nombres": ["Hernando Ruiz Vargas"],
        "cuotas_pendientes": [
            {
                "nro_cuota": 4,
                "fecha_vencimiento": "2026-01-01",
                "valor_cuota": 150000,
                "interes_mes": 18000,
                "cuota_mensual": 168000,
                "mora_estimada": 0,
                "estado": "vigente",
            },
        ],
    },
]

CAJA_INICIAL: dict = {
    "saldo_en_caja": 5830000,
    "total_admin": 270000,
    "porcentaje_mora": 0.02,
}

NOTIFICACIONES_INICIALES: list[dict] = [
    {
        "id": 1,
        "socio_id": 3,
        "numero_e164": "+573112223344",
        "texto": "Estimada María López, su aporte de $250.000 fue registrado el 2026-07-20. Gracias.",
        "estado": "pendiente",
        "fecha_creacion": "2026-07-20T10:00:00",
    }
]

_next_recibo_id = 100
_next_notif_id = 2


def make_nombre_completo(socio: dict) -> str:
    return f"{socio['nombres']} {socio['apellidos']}"


def get_initial_state() -> dict:
    """Retorna una copia profunda del estado inicial (para reset en tests)."""
    return {
        "socios": copy.deepcopy(SOCIOS_INICIALES),
        "creditos": copy.deepcopy(CREDITOS_INICIALES),
        "caja": copy.deepcopy(CAJA_INICIAL),
        "notificaciones": copy.deepcopy(NOTIFICACIONES_INICIALES),
        "recibos": [],
        "idempotency_keys": {},
        "next_recibo_id": 100,
        "next_notif_id": 2,
    }

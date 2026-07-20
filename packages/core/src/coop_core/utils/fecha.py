from datetime import date

_FECHA_SIMULADA: date | None = None


def get_hoy() -> date:
    if _FECHA_SIMULADA is not None:
        return _FECHA_SIMULADA
    return date.today()


def get_hoy_str() -> str:
    return get_hoy().strftime("%Y-%m-%d")


def set_fecha_simulada(nueva_fecha: date) -> None:
    global _FECHA_SIMULADA
    _FECHA_SIMULADA = nueva_fecha


def reset_fecha_normal() -> None:
    global _FECHA_SIMULADA
    _FECHA_SIMULADA = None

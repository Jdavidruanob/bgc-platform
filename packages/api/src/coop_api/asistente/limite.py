"""Freno anti-bucle del asistente de WhatsApp.

En octubre de 2026 el asistente quedó en ping-pong con otro sistema
automático: ~33 respuestas cada hora, día y noche, cobradas por Meta como
mensajes "Service", hasta que Meta cortaba con el error 131056 (pair rate
limit). Este módulo pone un tope de respuestas por número y descarta los
reintentos del mismo mensaje (mismo wamid).

Vive en memoria del proceso: la API corre en una sola instancia, y si se
reinicia el peor caso es que un número recupere su cupo antes de tiempo.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque

MAX_RESPUESTAS = 10
VENTANA_SEGUNDOS = 600
_MAX_WAMIDS = 2000


class LimitadorRespuestas:
    def __init__(
        self,
        max_respuestas: int = MAX_RESPUESTAS,
        ventana_segundos: float = VENTANA_SEGUNDOS,
    ) -> None:
        self._max = max_respuestas
        self._ventana = ventana_segundos
        self._ahora = time.monotonic  # reemplazable en tests
        self._por_numero: dict[str, deque[float]] = {}
        self._wamids: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.Lock()

    def ya_visto(self, wamid: str) -> bool:
        """True si este wamid ya se atendió (Meta reintentó el webhook)."""
        if not wamid:
            return False
        with self._lock:
            if wamid in self._wamids:
                return True
            self._wamids[wamid] = None
            if len(self._wamids) > _MAX_WAMIDS:
                self._wamids.popitem(last=False)
            return False

    def permitir(self, numero: str) -> bool:
        """Registra una respuesta a `numero` si aún tiene cupo en la ventana."""
        ahora = self._ahora()
        with self._lock:
            marcas = self._por_numero.setdefault(numero, deque())
            while marcas and ahora - marcas[0] >= self._ventana:
                marcas.popleft()
            if len(marcas) >= self._max:
                return False
            marcas.append(ahora)
            return True

    def reiniciar(self) -> None:
        with self._lock:
            self._por_numero.clear()
            self._wamids.clear()


limitador = LimitadorRespuestas()

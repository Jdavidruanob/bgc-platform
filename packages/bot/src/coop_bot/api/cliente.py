"""Cliente HTTP asíncrono de coop-api. Envuelve httpx, maneja errores e idempotencia."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx
from coop_contracts.respuestas import (
    AportesRequest,
    AportesResponse,
    CajaEstado,
    CombinadoResponse,
    CombinadosRequest,
    CreditosResponse,
    CuotasPendientesResponse,
    NotificacionesPendientesResponse,
    PagosRequest,
    PagosResponse,
    PatchNotificacionRequest,
    RetiroResponse,
    RetirosRequest,
    SocioDetalle,
    SociosSearchResponse,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_MENSAJE_POR_STATUS = {
    401: (
        "NO_AUTORIZADO",
        "No se pudo autenticar con la API. Contacta al desarrollador para revisar la conexión.",
    ),
}
_MENSAJE_ERROR_INTERNO = (
    "ERROR_INTERNO",
    "Ocurrió un error interno en el servidor. Intenta de nuevo en unos minutos.",
)


class ApiError(Exception):
    """Error devuelto por coop-api (o su mock), ya traducido a un mensaje en español."""

    def __init__(
        self,
        codigo: str,
        mensaje: str,
        status_code: int,
        detalle: object | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.status_code = status_code
        self.detalle = detalle


class ApiClient:
    """Cliente de coop-api. La URL base y el token se leen de `Config`, nunca hardcoded."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ApiClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ── Consultas ────────────────────────────────────────────────────────────

    async def buscar_socios(self, q: str, limit: int = 10) -> SociosSearchResponse:
        return await self._get("/socios", {"q": q, "limit": limit}, SociosSearchResponse)

    async def get_socio(self, socio_id: int) -> SocioDetalle:
        return await self._get(f"/socios/{socio_id}", {}, SocioDetalle)

    async def get_creditos_socio(self, socio_id: int) -> CreditosResponse:
        return await self._get(f"/socios/{socio_id}/creditos", {}, CreditosResponse)

    async def get_cuotas_pendientes(self, letra_id: int) -> CuotasPendientesResponse:
        return await self._get(f"/creditos/{letra_id}/cuotas-pendientes", {}, CuotasPendientesResponse)

    async def get_caja(self) -> CajaEstado:
        return await self._get("/caja", {}, CajaEstado)

    # ── Notificaciones ───────────────────────────────────────────────────────

    async def get_notificaciones_pendientes(self) -> NotificacionesPendientesResponse:
        return await self._get("/notificaciones/pendientes", {}, NotificacionesPendientesResponse)

    async def patch_notificacion(self, notificacion_id: int, estado: str, error: str | None = None) -> None:
        body = PatchNotificacionRequest(estado=estado, error=error)
        response = await self._pedir(
            lambda: self._client.patch(
                f"/notificaciones/{notificacion_id}", json=body.model_dump(mode="json")
            )
        )
        if response.is_error:
            self._lanzar_error(response)

    # ── Operaciones ──────────────────────────────────────────────────────────

    async def registrar_aportes(self, body: AportesRequest, idempotency_key: str) -> AportesResponse:
        return await self._post("/operaciones/aportes", body, idempotency_key, AportesResponse)

    async def registrar_retiro(self, body: RetirosRequest, idempotency_key: str) -> RetiroResponse:
        return await self._post("/operaciones/retiros", body, idempotency_key, RetiroResponse)

    async def registrar_pagos(self, body: PagosRequest, idempotency_key: str) -> PagosResponse:
        return await self._post("/operaciones/pagos", body, idempotency_key, PagosResponse)

    async def registrar_combinado(self, body: CombinadosRequest, idempotency_key: str) -> CombinadoResponse:
        return await self._post("/operaciones/combinados", body, idempotency_key, CombinadoResponse)

    # ── Test utilities ───────────────────────────────────────────────────────

    async def resetear_mock(self) -> None:
        """Solo para tests: reinicia el estado del mock server (`POST /test/reset`)."""
        await self._client.post("/test/reset")

    # ── Internos ─────────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any], modelo: type[T]) -> T:
        params_no_vacios = {k: v for k, v in params.items() if v not in (None, "")}
        response = await self._pedir(lambda: self._client.get(path, params=params_no_vacios))
        if response.is_error:
            self._lanzar_error(response)
        return modelo.model_validate(response.json())

    async def _post(self, path: str, body: BaseModel, idempotency_key: str, modelo: type[T]) -> T:
        response = await self._pedir(
            lambda: self._client.post(
                path,
                json=body.model_dump(mode="json"),
                headers={"Idempotency-Key": idempotency_key},
            )
        )
        if response.is_error:
            self._lanzar_error(response)
        return modelo.model_validate(response.json())

    async def _pedir(
        self, hacer_request: Callable[[], Coroutine[Any, Any, httpx.Response]]
    ) -> httpx.Response:
        try:
            return await hacer_request()
        except httpx.HTTPError as exc:
            raise ApiError(
                codigo="ERROR_DE_RED",
                mensaje="No se pudo conectar con el servidor. Intenta de nuevo en un momento.",
                status_code=0,
            ) from exc

    def _lanzar_error(self, response: httpx.Response) -> None:
        """Traduce el body de error del servidor a un ApiError.

        El mock (y la API real) no siempre usan el shape uniforme
        `{"error": {"codigo", "mensaje", "detalle"}}`: los errores de auth/
        idempotencia de FastAPI vienen como `{"detail": "texto plano"}`,
        mientras que los de negocio vienen como
        `{"detail": {"error": {...}}}`. Hay que soportar ambos.
        """
        try:
            body = response.json()
        except ValueError:
            body = None

        detail = body.get("detail", body) if isinstance(body, dict) else body

        if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
            error = detail["error"]
            raise ApiError(
                codigo=error.get("codigo", "ERROR_DESCONOCIDO"),
                mensaje=error.get("mensaje", "Ocurrió un error al llamar a la API."),
                status_code=response.status_code,
                detalle=error.get("detalle"),
            )

        if response.status_code in _MENSAJE_POR_STATUS:
            codigo, mensaje = _MENSAJE_POR_STATUS[response.status_code]
            raise ApiError(codigo=codigo, mensaje=mensaje, status_code=response.status_code)

        if response.status_code >= 500:
            codigo, mensaje = _MENSAJE_ERROR_INTERNO
            raise ApiError(codigo=codigo, mensaje=mensaje, status_code=response.status_code)

        mensaje = detail if isinstance(detail, str) else "Ocurrió un error al llamar a la API."
        raise ApiError(
            codigo="ERROR_DESCONOCIDO",
            mensaje=mensaje,
            status_code=response.status_code,
        )

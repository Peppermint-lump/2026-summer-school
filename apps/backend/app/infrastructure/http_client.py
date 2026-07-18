"""Small async HTTP boundary that keeps SDK types out of domain modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    data: dict[str, Any]
    request_id: str | None = None


class AsyncJsonClient(Protocol):
    async def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class HttpClientInvalidResponseError(ValueError):
    """The remote endpoint returned a response that is not a JSON object."""


class HttpxJsonClient:
    """HTTPX implementation created in infrastructure, never in the domain layer."""

    async def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> HttpResponse:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is not installed") from exc

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise TimeoutError("provider HTTP request timed out") from exc
        except httpx.RequestError as exc:
            raise OSError("provider HTTP request failed") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise HttpClientInvalidResponseError(
                "provider returned invalid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise HttpClientInvalidResponseError(
                "provider response must be a JSON object"
            )
        return HttpResponse(
            status_code=response.status_code,
            data=data,
            request_id=response.headers.get("x-request-id"),
        )

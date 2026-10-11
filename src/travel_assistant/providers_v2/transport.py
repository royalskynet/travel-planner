from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import httpx


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse: ...


class ResponseTooLargeError(OSError):
    pass


class HttpxTransport:
    """Bounded httpx transport. Redirects are deliberately never followed."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse:
        own_client = self._client is None
        client = self._client or httpx.Client(follow_redirects=False)
        try:
            with client.stream(
                method,
                url,
                headers=dict(headers or {}),
                content=body,
                timeout=timeout,
                follow_redirects=False,
            ) as response:
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ResponseTooLargeError(
                            f"response exceeds {max_bytes} bytes"
                        )
                    chunks.append(chunk)
                return HttpResponse(
                    response.status_code, b"".join(chunks), dict(response.headers)
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError("HTTP request timed out") from exc
        except httpx.RequestError as exc:
            raise OSError("HTTP request failed") from exc
        finally:
            if own_client:
                client.close()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Compatibility transport; new adapters default to HttpxTransport."""

    def __init__(self) -> None:
        self._opener = build_opener(_NoRedirect())

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse:
        request = Request(url, data=body, headers=dict(headers or {}), method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise ResponseTooLargeError(f"response exceeds {max_bytes} bytes")
                return HttpResponse(
                    response.status, payload, dict(response.headers.items())
                )
        except HTTPError as exc:
            payload = exc.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ResponseTooLargeError(
                    f"response exceeds {max_bytes} bytes"
                ) from exc
            return HttpResponse(exc.code, payload, dict(exc.headers.items()))

from __future__ import annotations

import json
import socket
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any

from .models import ProviderCapabilities, ProviderResult, ProviderStatus
from .transport import HttpResponse, ResponseTooLargeError


class FlightProvider(ABC):
    name: str
    capabilities: ProviderCapabilities

    @abstractmethod
    def search(self, request: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        raise NotImplementedError


def decode_json(response: HttpResponse) -> Any:
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise ValueError("provider returned invalid JSON") from exc


def failure_result(
    provider: str, exc: BaseException
) -> ProviderResult[list[dict[str, Any]]]:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        status, warning = ProviderStatus.TIMEOUT, "provider request timed out"
    elif isinstance(exc, ResponseTooLargeError):
        status, warning = ProviderStatus.PARSE_ERROR, str(exc)
    elif isinstance(exc, (OSError, ConnectionError)):
        status, warning = ProviderStatus.UNAVAILABLE, "provider is unavailable"
    elif isinstance(exc, (ValueError, TypeError, KeyError)):
        status, warning = (
            ProviderStatus.PARSE_ERROR,
            "provider response could not be parsed",
        )
    else:
        raise exc
    return ProviderResult(provider=provider, status=status, data=None, warning=warning)


def http_failure(
    provider: str, response: HttpResponse
) -> ProviderResult[list[dict[str, Any]]] | None:
    if 300 <= response.status_code < 400:
        return ProviderResult(
            provider, ProviderStatus.BLOCKED, warning="provider redirect was refused"
        )
    if response.status_code == 429:
        return ProviderResult(
            provider, ProviderStatus.RATE_LIMITED, warning="provider rate limit reached"
        )
    if response.status_code in {401, 403}:
        return ProviderResult(
            provider, ProviderStatus.AUTH_ERROR, warning="provider rejected credentials"
        )
    if response.status_code == 451:
        return ProviderResult(
            provider, ProviderStatus.BLOCKED, warning="provider blocked the request"
        )
    if response.status_code >= 500:
        return ProviderResult(
            provider, ProviderStatus.UNAVAILABLE, warning="provider service error"
        )
    if response.status_code >= 400:
        return ProviderResult(
            provider,
            ProviderStatus.PARSE_ERROR,
            warning=f"provider returned HTTP {response.status_code}",
        )
    return None

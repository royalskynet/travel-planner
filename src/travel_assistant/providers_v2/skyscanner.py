from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from .base import FlightProvider, decode_json, failure_result, http_failure
from .models import (
    Capability,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderResult,
    ProviderStatus,
)
from .request import validate_flight_request
from .transport import HttpTransport, HttpxTransport


class SkyscannerProvider(FlightProvider):
    name = "skyscanner"
    capabilities = ProviderCapabilities(
        frozenset(
            {
                Capability.LIVE_PRICES,
                Capability.MULTI_CITY,
                Capability.FLEXIBLE_DATES,
                Capability.FILTERS,
                Capability.BOOKING_LINKS,
            }
        )
    )
    base_url = "https://partners.api.skyscanner.net/apiservices/v3/flights/live/search"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        enabled: bool = False,
        transport: HttpTransport | None = None,
        timeout: float = 20,
        max_polls: int = 4,
        poll_interval: float = 0,
        sleeper: Callable[[float], None] = time.sleep,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        self.api_key = api_key
        self.enabled = enabled
        self.transport = transport or HttpxTransport()
        self.timeout = timeout
        self.max_polls = max_polls
        self.poll_interval = poll_interval
        self.sleeper = sleeper
        self.max_response_bytes = max_response_bytes

    def _credentials(self) -> str:
        if not self.enabled:
            raise ProviderConfigurationError(
                "Skyscanner provider is disabled until Partnerships approval"
            )
        key = self.api_key or os.environ.get("SKYSCANNER_API_KEY")
        if not key:
            raise ProviderConfigurationError("SKYSCANNER_API_KEY is required")
        return key

    @staticmethod
    def _normalize(body: dict[str, Any]) -> list[dict[str, Any]]:
        content = body.get("content") or {}
        results = content.get("results") or {}
        itineraries = results.get("itineraries") or {}
        values = itineraries.values() if isinstance(itineraries, dict) else itineraries
        if not isinstance(values, (list, tuple)) and not hasattr(values, "__iter__"):
            raise ValueError("itineraries must be iterable")
        return [
            dict(item, provider="skyscanner", is_live=True)
            for item in values
            if isinstance(item, dict)
        ]

    def _request(self, method: str, url: str, key: str, body: bytes | None = None):
        return self.transport.request(
            method,
            url,
            headers={
                "x-api-key": key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body=body,
            timeout=self.timeout,
            max_bytes=self.max_response_bytes,
        )

    def search(self, request: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        request = validate_flight_request(request)
        key = self._credentials()
        try:
            created = self._request(
                "POST",
                f"{self.base_url}/create",
                key,
                json.dumps(request).encode("utf-8"),
            )
            failure = http_failure(self.name, created)
            if failure:
                return failure
            body = decode_json(created)
            token = body.get("sessionToken")
            if not isinstance(token, str) or not token:
                raise ValueError("missing sessionToken")
            latest = body
            for attempt in range(self.max_polls + 1):
                status = str(latest.get("status", "")).upper()
                if status == "RESULT_STATUS_COMPLETE":
                    break
                if attempt >= self.max_polls:
                    return ProviderResult(
                        self.name,
                        ProviderStatus.TIMEOUT,
                        warning="Skyscanner session did not complete",
                    )
                if attempt and self.poll_interval:
                    self.sleeper(self.poll_interval)
                polled = self._request(
                    "POST", f"{self.base_url}/poll/{quote(token, safe='')}", key
                )
                failure = http_failure(self.name, polled)
                if failure:
                    return failure
                latest = decode_json(polled)
            offers = self._normalize(latest)
            return ProviderResult(
                self.name,
                ProviderStatus.OK if offers else ProviderStatus.EMPTY,
                offers,
                request_id=created.headers.get("x-request-id"),
            )
        except (TimeoutError, OSError, ValueError, TypeError, KeyError) as exc:
            return failure_result(self.name, exc)

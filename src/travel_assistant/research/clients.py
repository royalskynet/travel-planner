from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any, ClassVar
from urllib.parse import urlencode, urlparse

from travel_assistant.providers_v2.transport import (
    HttpTransport,
    HttpxTransport,
    ResponseTooLargeError,
)

from .safety import Resolver, _default_resolver, validate_public_https_url


class ResearchClientError(RuntimeError):
    pass


class ResearchHttpError(ResearchClientError):
    pass


class ResearchParseError(ResearchClientError):
    pass


def _retrieved_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_body(body: bytes, max_bytes: int) -> Any:
    if len(body) > max_bytes:
        raise ResponseTooLargeError(f"response exceeds {max_bytes} bytes")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise ResearchParseError("research service returned invalid JSON") from exc


class OSRMClient:
    PROFILES: ClassVar[frozenset[str]] = frozenset({"driving", "walking", "cycling"})

    def __init__(
        self,
        base_url: str = "https://router.project-osrm.org",
        *,
        transport: HttpTransport | None = None,
        resolver: Resolver = _default_resolver,
        timeout: float = 15,
        max_coordinates: int = 50,
        max_response_bytes: int = 1_000_000,
    ) -> None:
        base_url = base_url.rstrip("/")
        if (
            urlparse(base_url).hostname != "router.project-osrm.org"
            and transport is None
        ):
            raise ValueError(
                "custom OSRM endpoints require an explicitly injected transport"
            )
        self.base_url = validate_public_https_url(base_url, resolver=resolver)
        self.transport = transport or HttpxTransport()
        self.resolver = resolver
        self.timeout = timeout
        self.max_coordinates = max_coordinates
        self.max_response_bytes = max_response_bytes

    def matrix(
        self, coordinates: list[tuple[float, float]], *, profile: str = "walking"
    ) -> dict[str, Any]:
        validate_public_https_url(self.base_url, resolver=self.resolver)
        if profile not in self.PROFILES:
            raise ValueError(f"unsupported OSRM profile: {profile}")
        if not 2 <= len(coordinates) <= self.max_coordinates:
            raise ValueError(
                f"coordinates must contain 2..{self.max_coordinates} points"
            )
        encoded = []
        for latitude, longitude in coordinates:
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("coordinate is out of range")
            encoded.append(f"{longitude:.6f},{latitude:.6f}")
        url = (
            f"{self.base_url}/table/v1/{profile}/"
            + ";".join(encoded)
            + "?annotations=duration,distance"
        )
        response = self.transport.request(
            "GET",
            url,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            max_bytes=self.max_response_bytes,
        )
        if response.status_code == 429:
            raise ResearchHttpError("OSRM rate limited the request")
        if not 200 <= response.status_code < 300:
            raise ResearchHttpError(f"OSRM returned HTTP {response.status_code}")
        body = _json_body(response.body, self.max_response_bytes)
        if body.get("code") != "Ok" or not isinstance(body.get("durations"), list):
            raise ResearchParseError("OSRM response is missing a duration matrix")
        return {
            "provider": "osrm",
            "status": "ok",
            "retrieved_at": _retrieved_at(),
            "durations": body["durations"],
            "distances": body.get("distances"),
            "estimated": False,
        }


class OverpassClient:
    TAG = re.compile(r"^[A-Za-z0-9_:-]{1,64}$")

    def __init__(
        self,
        base_url: str = "https://overpass-api.de/api/interpreter",
        *,
        transport: HttpTransport | None = None,
        resolver: Resolver = _default_resolver,
        timeout: float = 25,
        max_query_chars: int = 12_000,
        max_elements: int = 200,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        if urlparse(base_url).hostname != "overpass-api.de" and transport is None:
            raise ValueError(
                "custom Overpass endpoints require an explicitly injected transport"
            )
        self.base_url = validate_public_https_url(base_url, resolver=resolver)
        self.transport = transport or HttpxTransport()
        self.resolver = resolver
        self.timeout = timeout
        self.max_query_chars = max_query_chars
        self.max_elements = max_elements
        self.max_response_bytes = max_response_bytes

    def query(self, query: str) -> dict[str, Any]:
        validate_public_https_url(self.base_url, resolver=self.resolver)
        if not query or len(query) > self.max_query_chars:
            raise ValueError(
                f"Overpass query must contain 1..{self.max_query_chars} characters"
            )
        body = urlencode({"data": query}).encode("utf-8")
        response = self.transport.request(
            "POST",
            self.base_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=body,
            timeout=self.timeout,
            max_bytes=self.max_response_bytes,
        )
        if response.status_code == 429:
            raise ResearchHttpError("Overpass rate limited the request")
        if not 200 <= response.status_code < 300:
            raise ResearchHttpError(f"Overpass returned HTTP {response.status_code}")
        parsed = _json_body(response.body, self.max_response_bytes)
        elements = parsed.get("elements")
        if not isinstance(elements, list):
            raise ResearchParseError("Overpass response is missing elements")
        return {
            "provider": "overpass",
            "status": "ok",
            "retrieved_at": _retrieved_at(),
            "elements": elements[: self.max_elements],
            "truncated": len(elements) > self.max_elements,
            "result_count": min(len(elements), self.max_elements),
        }

    def search_pois(
        self,
        latitude: float,
        longitude: float,
        *,
        radius_m: int = 5_000,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("coordinate is out of range")
        if not 1 <= radius_m <= 50_000:
            raise ValueError("radius_m must be 1..50000")
        tags = tags or {"tourism": "attraction"}
        filters = []
        for key, value in tags.items():
            if not self.TAG.fullmatch(key) or not self.TAG.fullmatch(value):
                raise ValueError("OSM tag contains unsupported characters")
            filters.append(f'["{key}"="{value}"]')
        selector = "".join(filters)
        around = f"(around:{radius_m},{latitude:.6f},{longitude:.6f})"
        query = (
            f"[out:json][timeout:{max(1, int(self.timeout))}];("
            f"node{selector}{around};way{selector}{around};relation{selector}{around};"
            ");out center tags;"
        )
        return self.query(query)

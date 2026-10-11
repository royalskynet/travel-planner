from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from urllib.parse import urlencode

from .base import FlightProvider
from .models import (
    Capability,
    ExperimentalProviderDisabled,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderResult,
    ProviderStatus,
)
from .request import validate_flight_request


def google_flights_deep_link(request: dict[str, Any]) -> str:
    request = validate_flight_request(request)
    slices = request["slices"]
    phrases = [
        f"{item['origin']} to {item['destination']} on {date.fromisoformat(item['departure_date']).isoformat()}"
        for item in slices
    ]
    query = "Flights " + ", then ".join(phrases)
    params = {"q": query, "curr": request.get("currency", "USD")}
    if request.get("language"):
        params["hl"] = request["language"]
    return "https://www.google.com/travel/flights?" + urlencode(params)


class GoogleFlightsLinkProvider:
    name = "google-link"
    capabilities = ProviderCapabilities(
        frozenset({Capability.MULTI_CITY, Capability.BOOKING_LINKS})
    )

    def search(self, request: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        request = validate_flight_request(request)
        return ProviderResult(
            self.name,
            status=ProviderStatus.OK,
            data=[
                {
                    "provider": self.name,
                    "booking_url": google_flights_deep_link(request),
                    "is_live": False,
                    "warning": "查詢連結，不代表即時價格或可訂位狀態",
                }
            ],
        )


class FliExperimentalProvider(FlightProvider):
    name = "fli-experimental"
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

    def __init__(
        self,
        *,
        enabled: bool = False,
        live_adapter: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.enabled = enabled
        self.live_adapter = live_adapter

    def search(self, request: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        request = validate_flight_request(request)
        if not self.enabled:
            raise ExperimentalProviderDisabled(
                "fli live search is disabled by default; use google-link or an official provider"
            )
        if self.live_adapter is None:
            raise ProviderConfigurationError(
                "fli requires an explicitly injected isolated live adapter"
            )
        items = self.live_adapter(request)
        return ProviderResult(
            self.name,
            ProviderStatus.OK if items else ProviderStatus.EMPTY,
            [
                dict(item, provider=self.name, is_live=True, experimental=True)
                for item in items
            ],
            warning="Unofficial reverse-engineered source; recheck before purchase",
        )

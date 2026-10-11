from __future__ import annotations

from typing import Any

from .base import FlightProvider
from .models import Capability, ProviderCapabilities, ProviderResult, ProviderStatus
from .request import validate_flight_request


class MockFlightProvider(FlightProvider):
    """Deterministic offline handoff; deliberately never invents a fare."""

    name = "mock"
    capabilities = ProviderCapabilities(frozenset({Capability.MULTI_CITY}))

    def search(self, request: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        request = validate_flight_request(request)
        slices = request["slices"]
        normalized = [
            {
                "origin": item["origin"],
                "destination": item["destination"],
                "departure_date": item["departure_date"],
            }
            for item in slices
        ]
        warning = "離線示例，未查詢即時價格或可訂位狀態"
        return ProviderResult(
            self.name,
            ProviderStatus.OK,
            [
                {
                    "provider": self.name,
                    "slices": normalized,
                    "price": None,
                    "currency": request.get("currency"),
                    "is_live": False,
                    "warning": warning,
                }
            ],
            warning=warning,
        )

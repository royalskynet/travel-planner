from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any

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


class DuffelProvider(FlightProvider):
    name = "duffel"
    capabilities = ProviderCapabilities(
        frozenset({Capability.LIVE_PRICES, Capability.MULTI_CITY, Capability.FILTERS})
    )
    endpoint = "https://api.duffel.com/air/offer_requests?return_offers=true"

    def __init__(
        self,
        token: str | None = None,
        *,
        transport: HttpTransport | None = None,
        timeout: float = 20,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        self.token = token
        self.transport = transport or HttpxTransport()
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    @staticmethod
    def build_payload(request: dict[str, Any]) -> dict[str, Any]:
        request = validate_flight_request(request)
        passengers = [{"type": "adult"} for _ in range(request["adults"])]
        passengers += [{"type": "child"} for _ in range(request["children"])]
        passengers += [
            {"type": "infant_without_seat"} for _ in range(request["infants"])
        ]
        return {
            "data": {
                "slices": request["slices"],
                "passengers": passengers,
                "cabin_class": request.get("cabin_class", "economy"),
            }
        }

    @staticmethod
    def _normalize_offer(offer: dict[str, Any]) -> dict[str, Any]:
        try:
            amount = Decimal(str(offer["total_amount"]))
        except (KeyError, InvalidOperation) as exc:
            raise ValueError("Duffel offer has an invalid price") from exc
        currency = offer.get("total_currency")
        if (
            not amount.is_finite()
            or amount <= 0
            or not isinstance(currency, str)
            or len(currency) != 3
        ):
            raise ValueError("Duffel offer has an invalid price")
        slices: list[dict[str, Any]] = []
        for flight_slice in offer.get("slices", []):
            segments = []
            for segment in flight_slice.get("segments", []):
                segments.append(
                    {
                        "origin": segment.get("origin", {}).get("iata_code"),
                        "destination": segment.get("destination", {}).get("iata_code"),
                        "departing_at": segment.get("departing_at"),
                        "arriving_at": segment.get("arriving_at"),
                        "marketing_carrier": segment.get("marketing_carrier", {}).get(
                            "iata_code"
                        ),
                        "flight_number": segment.get("marketing_carrier_flight_number"),
                    }
                )
            slices.append(
                {"duration": flight_slice.get("duration"), "segments": segments}
            )
        return {
            "provider": "duffel",
            "offer_id": offer.get("id"),
            "total_amount": str(offer["total_amount"]),
            "total_currency": currency,
            "expires_at": offer.get("expires_at"),
            "owner": offer.get("owner", {}).get("name"),
            "slices": slices,
            "is_live": True,
        }

    def search(self, request: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        request = validate_flight_request(request)
        token = self.token or os.environ.get("DUFFEL_ACCESS_TOKEN")
        if not token:
            raise ProviderConfigurationError("DUFFEL_ACCESS_TOKEN is required")
        payload = self.build_payload(request)
        try:
            response = self.transport.request(
                "POST",
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Duffel-Version": "v2",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body=json.dumps(payload).encode("utf-8"),
                timeout=self.timeout,
                max_bytes=self.max_response_bytes,
            )
            failure = http_failure(self.name, response)
            if failure:
                return failure
            body = decode_json(response)
            offers = body["data"].get("offers", [])
            if not isinstance(offers, list):
                raise TypeError("offers must be a list")
            normalized = [self._normalize_offer(offer) for offer in offers]
            status = ProviderStatus.OK if normalized else ProviderStatus.EMPTY
            return ProviderResult(
                self.name,
                status,
                normalized,
                request_id=response.headers.get("x-request-id"),
            )
        except (TimeoutError, OSError, ValueError, TypeError, KeyError) as exc:
            return failure_result(self.name, exc)

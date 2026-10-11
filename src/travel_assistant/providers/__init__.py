from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from urllib.request import Request, urlopen


class FlightProvider(ABC):
    @abstractmethod
    def search(self, request: dict) -> list[dict]:
        raise NotImplementedError


class MockFlightProvider(FlightProvider):
    def search(self, request: dict) -> list[dict]:
        return [{"provider": "mock", "origin": request["origin"], "destination": request["destination"], "departure_date": request["departure_date"], "price": 0, "currency": request.get("currency", "TWD"), "note": "示例航班，需重新查證"}]


class DuffelFlightProvider(FlightProvider):
    def search(self, request: dict) -> list[dict]:
        token = os.environ.get("DUFFEL_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("DUFFEL_ACCESS_TOKEN is required")
        payload = {"data": {"slices": [{"origin": request["origin"], "destination": request["destination"], "departure_date": request["departure_date"]}], "passengers": [{"type": "adult"}] * request.get("travellers", 1), "cabin_class": request.get("cabin_class", "economy")}}
        req = Request("https://api.duffel.com/air/offer_requests?return_offers=true", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Duffel-Version": "v2", "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        with urlopen(req, timeout=20) as response:
            body = json.load(response)
        return [{"provider": "duffel", "offer_id": offer.get("id"), "total_amount": offer.get("total_amount"), "total_currency": offer.get("total_currency"), "expires_at": offer.get("expires_at"), "owner": offer.get("owner", {}).get("name")} for offer in body.get("data", {}).get("offers", [])]


class SkyscannerFlightProvider(FlightProvider):
    def search(self, request: dict) -> list[dict]:
        if not os.environ.get("SKYSCANNER_API_KEY"):
            raise RuntimeError("Skyscanner adapter requires an approved Partnerships account and SKYSCANNER_API_KEY")
        raise RuntimeError("Skyscanner adapter is intentionally disabled until official Partnerships approval and endpoint configuration")

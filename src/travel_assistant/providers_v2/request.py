from __future__ import annotations

import re
from datetime import date
from typing import Any

from .models import ProviderParseError

IATA = re.compile(r"^[A-Z]{3}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CABIN_CLASSES = {"economy", "premium_economy", "business", "first"}
MAX_PASSENGERS = 9


def _passenger_count(request: dict[str, Any], field: str, default: int) -> int:
    value = request.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderParseError(f"{field} must be a non-negative integer")
    return value


def validate_flight_request(request: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized request or one stable provider-boundary error."""

    try:
        if not isinstance(request, dict):
            raise ProviderParseError("flight request must be an object")
        raw_slices = request.get("slices")
        if raw_slices is None and any(
            field in request for field in ("origin", "destination", "departure_date")
        ):
            raw_slices = [
                {
                    "origin": request.get("origin"),
                    "destination": request.get("destination"),
                    "departure_date": request.get("departure_date"),
                }
            ]
        if not isinstance(raw_slices, list) or not raw_slices:
            raise ProviderParseError("slices must be a non-empty list")

        slices: list[dict[str, str]] = []
        departure_dates: list[date] = []
        for index, item in enumerate(raw_slices):
            if not isinstance(item, dict):
                raise ProviderParseError(f"slices[{index}] must be an object")
            origin = item.get("origin")
            destination = item.get("destination")
            departure_date = item.get("departure_date")
            if not isinstance(origin, str) or not IATA.fullmatch(origin):
                raise ProviderParseError(
                    f"slices[{index}].origin must be a three-letter uppercase IATA code"
                )
            if not isinstance(destination, str) or not IATA.fullmatch(destination):
                raise ProviderParseError(
                    f"slices[{index}].destination must be a three-letter uppercase IATA code"
                )
            if not isinstance(departure_date, str) or not ISO_DATE.fullmatch(
                departure_date
            ):
                raise ProviderParseError(
                    f"slices[{index}].departure_date must be an ISO date"
                )
            try:
                parsed_date = date.fromisoformat(departure_date)
            except ValueError as exc:
                raise ProviderParseError(
                    f"slices[{index}].departure_date must be a valid ISO date"
                ) from exc
            slices.append(
                {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date,
                }
            )
            departure_dates.append(parsed_date)
        if departure_dates != sorted(departure_dates):
            raise ProviderParseError("slice departure dates must be chronological")
        first, last = slices[0], slices[-1]
        is_round_trip = (
            len(slices) > 1
            and last["origin"] == first["destination"]
            and last["destination"] == first["origin"]
        )
        if is_round_trip and departure_dates[-1] <= departure_dates[0]:
            raise ProviderParseError(
                "return departure_date must be after outbound departure_date"
            )

        legacy_travellers = request.get("travellers", 1)
        if isinstance(legacy_travellers, bool) or not isinstance(
            legacy_travellers, int
        ):
            raise ProviderParseError("travellers must be a non-negative integer")
        adults = _passenger_count(request, "adults", legacy_travellers)
        children = _passenger_count(request, "children", 0)
        infants = _passenger_count(request, "infants", 0)
        total = adults + children + infants
        if total <= 0:
            raise ProviderParseError("at least one traveller is required")
        if total > MAX_PASSENGERS:
            raise ProviderParseError(
                f"total travellers must not exceed {MAX_PASSENGERS}"
            )
        if infants > adults:
            raise ProviderParseError("infants must not exceed adults")

        cabin_class = request.get("cabin_class", "economy")
        if cabin_class not in CABIN_CLASSES:
            raise ProviderParseError(
                "cabin_class must be economy, premium_economy, business or first"
            )
        currency = request.get("currency", "USD")
        if not isinstance(currency, str) or not CURRENCY.fullmatch(currency):
            raise ProviderParseError("currency must be three uppercase letters")
    except ProviderParseError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderParseError("invalid flight request") from exc

    normalized = dict(request)
    normalized.update(
        {
            "slices": slices,
            "adults": adults,
            "children": children,
            "infants": infants,
            "cabin_class": cabin_class,
            "currency": currency,
        }
    )
    return normalized

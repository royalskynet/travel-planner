"""Route matrix boundary and deterministic geographic fallback."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from travel_assistant.domain import GeoPoint


@dataclass(frozen=True)
class RouteEstimate:
    minutes: int
    distance_km: float
    provider: str
    estimated: bool


class RouteMatrix(Protocol):
    def estimate(self, origin: GeoPoint, destination: GeoPoint, *, mode: str = "walking") -> RouteEstimate:
        """Return one bounded route estimate without mutating trip state."""


def haversine_km(origin: GeoPoint, destination: GeoPoint) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    delta_lat = math.radians(destination.latitude - origin.latitude)
    delta_lon = math.radians(destination.longitude - origin.longitude)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class HaversineRouteMatrix:
    """Straight-line fallback with configurable effective speeds."""

    SPEED_KMH = {"walking": 4.5, "cycling": 14.0, "driving": 30.0, "transit": 22.0}

    def __init__(self, *, minimum_minutes: int = 5, distance_factor: float = 1.25) -> None:
        self.minimum_minutes = minimum_minutes
        self.distance_factor = distance_factor

    def estimate(self, origin: GeoPoint, destination: GeoPoint, *, mode: str = "walking") -> RouteEstimate:
        if mode not in self.SPEED_KMH:
            raise ValueError(f"unsupported route mode: {mode}")
        distance = haversine_km(origin, destination)
        if distance < 0.02:
            minutes = 0
        else:
            minutes = max(self.minimum_minutes, math.ceil(distance * self.distance_factor / self.SPEED_KMH[mode] * 60))
        return RouteEstimate(minutes=minutes, distance_km=round(distance, 3), provider="haversine", estimated=True)

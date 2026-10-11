"""V2 normalized travel domain models and V1 migration helpers."""

from .migration import migrate_v1
from .models import (
    Activity,
    ChecklistItem,
    Day,
    Expense,
    FlightSegment,
    GeoPoint,
    OpeningWindow,
    Place,
    Reservation,
    SourceSnapshot,
    Stay,
    TravelLeg,
    Trip,
)

__all__ = [
    "Activity",
    "ChecklistItem",
    "Day",
    "Expense",
    "FlightSegment",
    "GeoPoint",
    "OpeningWindow",
    "Place",
    "Reservation",
    "SourceSnapshot",
    "Stay",
    "TravelLeg",
    "Trip",
    "migrate_v1",
]

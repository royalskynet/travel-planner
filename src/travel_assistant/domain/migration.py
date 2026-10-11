"""Migration from the original single-destination JSON input to V2."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List

from .models import (
    Activity,
    Day,
    Expense,
    FlightSegment,
    GeoPoint,
    OpeningWindow,
    Place,
    SourceSnapshot,
    Trip,
)


def _identifier(prefix: str, value: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or str(index + 1)
    return f"{prefix}-{index + 1}-{slug}"


def migrate_v1(data: Dict[str, Any], *, trip_id: str = "trip-v1") -> Trip:
    """Convert a validated-or-raw V1 input without losing activities or route.

    V1 had no departure time. Noon UTC is explicitly an estimated placeholder;
    consumers must not present it as a real flight schedule.
    """

    start_date = data["start_date"]
    activities: List[Activity] = []
    places: List[Place] = []
    sources: List[SourceSnapshot] = []
    expenses: List[Expense] = []
    for index, raw in enumerate(data.get("activities", [])):
        activity_id = _identifier("activity", raw["name"], index)
        place_id = _identifier("place", raw["name"], index)
        source_id = f"source-{index + 1}"
        places.append(
            Place(
                id=place_id,
                name=raw["name"],
                location=GeoPoint(latitude=raw["latitude"], longitude=raw["longitude"]),
                source_ids=[source_id],
            )
        )
        windows = [
            OpeningWindow(weekday=weekday, start=time(0, 0), end=time(23, 59))
            for weekday in raw.get("open_weekdays", range(1, 8))
        ]
        activities.append(
            Activity(
                id=activity_id,
                name=raw["name"],
                place_id=place_id,
                duration_minutes=raw["duration_minutes"],
                opening_windows=windows,
                tags=raw.get("interests", []),
                source_ids=[source_id],
            )
        )
        sources.append(
            SourceSnapshot(
                id=source_id,
                url=raw["source_url"],
                provider="v1-input",
                checked_at=raw["checked_at"],
                status="verified",
            )
        )
        if raw.get("cost", 0):
            expenses.append(
                Expense(
                    id=f"expense-{index + 1}",
                    category="activity",
                    amount=raw["cost"],
                    currency=data["currency"],
                    description=raw["name"],
                    source_id=source_id,
                )
            )

    estimated_departure = datetime.fromisoformat(f"{start_date}T12:00:00+00:00")
    checked_values = []
    for raw in data.get("activities", []):
        checked = datetime.fromisoformat(str(raw["checked_at"]).replace("Z", "+00:00"))
        checked_values.append(checked.replace(tzinfo=timezone.utc) if checked.tzinfo is None else checked.astimezone(timezone.utc))
    migration_checked_at = min(checked_values) if checked_values else datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    route_source = SourceSnapshot(
        id="source-v1-route",
        url=None,
        provider="v1-migration",
        checked_at=migration_checked_at,
        status="estimated",
        facts={"reason": "V1 contained dates and airports but no flight time"},
    )
    sources.append(route_source)
    start_day = date.fromisoformat(data["start_date"])
    end_day = date.fromisoformat(data["end_date"])
    return Trip(
        id=trip_id,
        title=f"{data['origin']} → {data['destination']}",
        start_date=data["start_date"],
        end_date=data["end_date"],
        travellers=data.get("travellers", 1),
        currency=data.get("currency", "USD"),
        budget=data.get("budget"),
        interests=data.get("interests", []),
        places=places,
        days=[Day(on_date=start_day + timedelta(days=offset)) for offset in range((end_day - start_day).days + 1)],
        flight_segments=[
            FlightSegment(
                id="flight-segment-1",
                origin=data["origin"],
                destination=data["destination"],
                departure=estimated_departure,
                source_id=route_source.id,
            )
        ],
        activities=activities,
        expenses=expenses,
        sources=sources,
    )

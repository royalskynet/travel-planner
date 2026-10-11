from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any

SECRET_KEYS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
    "accesstoken",
    "client_secret",
    "refresh_token",
    "session_token",
    "sessiontoken",
}


def _is_secret_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in SECRET_KEYS or normalized.endswith(
        ("_api_key", "_password", "_secret", "_token")
    )


def to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {
            str(key): to_plain(item)
            for key, item in value.items()
            if not _is_secret_key(key)
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def trip_days(trip: Any) -> list[dict[str, Any]]:
    data = to_plain(trip)
    days = data.get("days") or data.get("itinerary") or []
    return [day for day in days if isinstance(day, dict)]


def day_items(day: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = day.get("items") or day.get("activities") or day.get("timeline") or []
    return [item for item in items if isinstance(item, dict)]


def _coordinate(item: Mapping[str, Any]) -> tuple[float, float] | None:
    place = item.get("place") if isinstance(item.get("place"), Mapping) else {}
    latitude = item.get("latitude", place.get("latitude"))
    longitude = item.get("longitude", place.get("longitude"))
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return latitude, longitude
    return None


def iter_locations(
    trip: Any,
) -> Iterator[tuple[dict[str, Any], str, int, tuple[float, float]]]:
    for day in trip_days(trip):
        day_date = str(day.get("date", ""))
        for order, item in enumerate(day_items(day), 1):
            coordinate = _coordinate(item)
            if coordinate is not None:
                yield item, day_date, order, coordinate


def parse_start(day_date: str, item: Mapping[str, Any]) -> tuple[datetime | date, bool]:
    raw = item.get("start_at") or item.get("start")
    if raw:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed, False
    raw_time = item.get("start_time")
    if raw_time:
        return datetime.combine(
            date.fromisoformat(day_date), time.fromisoformat(str(raw_time))
        ), False
    return date.fromisoformat(day_date), True


def parse_end(
    start: datetime | date, all_day: bool, item: Mapping[str, Any]
) -> datetime | date:
    raw = item.get("end_at") or item.get("end")
    if raw:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if all_day:
        return start + timedelta(days=1)
    return start + timedelta(minutes=int(item.get("duration_minutes", 60)))

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse
import re

IATA = re.compile(r"^[A-Z]{3}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
PACE_LIMITS = {"slow": 240, "moderate": 360, "fast": 480}


class ValidationError(ValueError):
    pass


def _url(value: Any, field: str) -> str:
    if not isinstance(value, str) or urlparse(value).scheme not in {"http", "https"}:
        raise ValidationError(f"{field} must be an http(s) URL")
    return value


def _checked_at(value: Any, field: str = "checked_at") -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an ISO datetime")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an ISO datetime") from exc
    return value


def _number(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a number")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValidationError(f"{field} is out of range")
    return value


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValidationError(f"{field} must be a list of non-empty strings")
    return value


def validate_input(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("input must be an object")
    try:
        origin, destination = data["origin"], data["destination"]
        start, end = date.fromisoformat(data["start_date"]), date.fromisoformat(data["end_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("origin, destination, start_date and end_date are required") from exc
    if not (isinstance(origin, str) and IATA.fullmatch(origin) and isinstance(destination, str) and IATA.fullmatch(destination)):
        raise ValidationError("origin and destination must be three uppercase IATA letters")
    if start > end:
        raise ValidationError("start_date must not be after end_date")
    _number(data.get("travellers"), "travellers", minimum=1)
    if not isinstance(data.get("travellers"), int) or isinstance(data["travellers"], bool):
        raise ValidationError("travellers must be a positive integer")
    _number(data.get("budget"), "budget", minimum=0)
    if not isinstance(data.get("currency"), str) or not CURRENCY.fullmatch(data["currency"]):
        raise ValidationError("currency must be three uppercase letters")
    if data.get("pace", "moderate") not in PACE_LIMITS:
        raise ValidationError("pace must be slow, moderate or fast")
    _strings(data.get("interests", []), "interests")
    activities = data.get("activities", [])
    if not isinstance(activities, list):
        raise ValidationError("activities must be a list")
    for activity in activities:
        if not isinstance(activity, dict):
            raise ValidationError("activity must be an object")
        name = activity.get("name", "<unnamed>")
        if not isinstance(name, str) or not name:
            raise ValidationError("activity name must be a non-empty string")
        for field in ("source_url", "checked_at"):
            if not activity.get(field):
                raise ValidationError(f"activity {name} missing {field}")
        _url(activity["source_url"], "source_url")
        _checked_at(activity["checked_at"])
        _number(activity.get("duration_minutes"), "duration_minutes", minimum=1)
        if not isinstance(activity["duration_minutes"], int) or isinstance(activity["duration_minutes"], bool):
            raise ValidationError("duration_minutes must be a positive integer")
        _number(activity.get("cost", 0), "cost", minimum=0)
        _number(activity.get("latitude"), "latitude", minimum=-90, maximum=90)
        _number(activity.get("longitude"), "longitude", minimum=-180, maximum=180)
        _strings(activity.get("interests", []), "activity interests")
        weekdays = activity.get("open_weekdays", list(range(1, 8)))
        if not isinstance(weekdays, list) or not weekdays or not all(isinstance(day, int) and not isinstance(day, bool) and 1 <= day <= 7 for day in weekdays):
            raise ValidationError("open_weekdays must be a non-empty list of ISO weekdays")


def schedule(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_input(data)
    start, end = date.fromisoformat(data["start_date"]), date.fromisoformat(data["end_date"])
    days = [(start.fromordinal(start.toordinal() + i), []) for i in range((end - start).days + 1)]
    remaining = list(enumerate(data.get("activities", [])))
    interests = set(data.get("interests", []))
    limit = PACE_LIMITS[data.get("pace", "moderate")]
    chosen: set[int] = set()
    for day, items in days:
        used = 0
        weekday = day.isoweekday()
        candidates = sorted(remaining, key=lambda pair: (-len(interests.intersection(pair[1].get("interests", []))), pair[0]))
        for index, activity in candidates:
            if index in chosen or weekday not in activity.get("open_weekdays", list(range(1, 8))):
                continue
            duration = activity["duration_minutes"]
            if used + duration <= limit:
                items.append({"name": activity["name"], "duration_minutes": duration, "cost": activity.get("cost", 0), "source_url": activity["source_url"], "checked_at": activity["checked_at"]})
                used += duration
                chosen.add(index)
    itinerary = [{"date": day.isoformat(), "activities": items, "minutes": sum(x["duration_minutes"] for x in items), "activity_cost": sum(x["cost"] for x in items)} for day, items in days]
    return itinerary, [activity for index, activity in remaining if index not in chosen]

"""Deterministic time-window and route-aware scheduling."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Literal, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from travel_assistant.domain import (
    Activity,
    GeoPoint,
    OpeningWindow,
    Place,
    Trip,
)

from .routing import HaversineRouteMatrix, RouteEstimate, RouteMatrix, haversine_km


class PlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScheduledItem(PlanningModel):
    id: str
    kind: Literal["activity", "reservation", "flight", "stay"]
    name: str
    place_id: Optional[str]
    start: datetime
    end: datetime
    locked: bool
    travel_from_previous_minutes: int = Field(default=0, ge=0)
    travel_estimated: bool = False


class PlanDay(PlanningModel):
    date: date
    items: List[ScheduledItem] = Field(default_factory=list)


class Conflict(PlanningModel):
    code: Literal[
        "fixed_overlap",
        "travel_time_collision",
        "outside_trip",
        "closed",
        "window_too_short",
        "locked_without_slot",
    ]
    item_ids: List[str]
    on_date: Optional[date] = None
    message: str


class Explanation(PlanningModel):
    item_id: str
    code: str
    message: str


class PlanResult(PlanningModel):
    trip_id: str
    days: List[PlanDay]
    unscheduled_activity_ids: List[str] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    explanations: List[Explanation] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown trip timezone: {name}") from exc


def _localized(value: datetime, zone: ZoneInfo) -> datetime:
    return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)


def _combine(day: date, value: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, value).replace(tzinfo=zone)


def _windows(
    activity: Activity,
    day: date,
    zone: ZoneInfo,
    day_start: time,
    day_end: time,
    *,
    restrict_to_day: bool = True,
) -> List[Tuple[datetime, datetime]]:
    lower_bound = day_start if restrict_to_day else time.min
    upper_bound = day_end if restrict_to_day else time.max
    if not activity.opening_windows:
        raw = [(lower_bound, upper_bound)]
    else:
        dated = [window for window in activity.opening_windows if window.on_date == day]
        selected: Sequence[OpeningWindow] = dated or [
            window for window in activity.opening_windows if window.on_date is None and window.weekday == day.isoweekday()
        ]
        raw = [(window.start, window.end) for window in selected]
    result: List[Tuple[datetime, datetime]] = []
    for start, end in raw:
        start = max(start, activity.earliest_start or lower_bound, lower_bound)
        effective_latest = activity.latest_start
        start_dt = _combine(day, start, zone)
        end_dt = _combine(day, min(end, upper_bound), zone)
        if effective_latest is not None:
            latest_end = _combine(day, effective_latest, zone) + timedelta(minutes=activity.duration_minutes)
            end_dt = min(end_dt, latest_end)
        if start_dt < end_dt:
            result.append((start_dt, end_dt))
    return sorted(result)


def _safe_route(
    matrix: RouteMatrix,
    fallback: HaversineRouteMatrix,
    origin: Optional[GeoPoint],
    destination: Optional[GeoPoint],
    warnings: List[str],
) -> RouteEstimate:
    if origin is None or destination is None:
        return RouteEstimate(minutes=0, distance_km=0.0, provider="none", estimated=False)
    try:
        return matrix.estimate(origin, destination, mode="walking")
    except Exception as exc:
        warning = f"route matrix unavailable ({type(exc).__name__}); used haversine estimate"
        if warning not in warnings:
            warnings.append(warning)
        return fallback.estimate(origin, destination, mode="walking")


def _stay_place(trip: Trip, day: date, zone: ZoneInfo) -> Optional[str]:
    for stay in trip.stays:
        if _localized(stay.check_in, zone).date() <= day < _localized(stay.check_out, zone).date():
            return stay.place_id
    return None


def _anchor_items(trip: Trip, zone: ZoneInfo, conflicts: List[Conflict]) -> Dict[date, List[ScheduledItem]]:
    result: Dict[date, List[ScheduledItem]] = {}
    for activity in trip.activities:
        fixed = activity.fixed_start or (activity.scheduled_start if activity.locked else None)
        if fixed is None:
            continue
        fixed = _localized(fixed, zone)
        item = ScheduledItem(
            id=activity.id,
            kind="activity",
            name=activity.name,
            place_id=activity.place_id,
            start=fixed,
            end=fixed + timedelta(minutes=activity.duration_minutes),
            locked=True,
        )
        if not (trip.start_date <= fixed.date() <= trip.end_date):
            conflicts.append(Conflict(code="outside_trip", item_ids=[activity.id], on_date=fixed.date(), message="固定活動在旅程日期之外"))
        else:
            result.setdefault(fixed.date(), []).append(item)
    for reservation in trip.reservations:
        if reservation.status == "cancelled":
            continue
        start = _localized(reservation.starts_at, zone)
        end = _localized(reservation.ends_at, zone) if reservation.ends_at else start + timedelta(minutes=60)
        item = ScheduledItem(
            id=reservation.id,
            kind="reservation",
            name=reservation.name,
            place_id=reservation.place_id,
            start=start,
            end=end,
            locked=True,
        )
        if not (trip.start_date <= start.date() <= trip.end_date):
            conflicts.append(Conflict(code="outside_trip", item_ids=[reservation.id], on_date=start.date(), message="預約在旅程日期之外"))
        else:
            result.setdefault(start.date(), []).append(item)
    for segment in trip.flight_segments:
        if segment.arrival is None:
            continue
        departure = _localized(segment.departure, zone)
        arrival = _localized(segment.arrival, zone)
        cursor = max(trip.start_date, departure.date())
        final_day = min(trip.end_date, arrival.date())
        while cursor <= final_day:
            day_floor = _combine(cursor, time.min, zone)
            next_floor = day_floor + timedelta(days=1)
            start = max(departure, day_floor)
            end = min(arrival, next_floor)
            if start < end:
                suffix = "" if cursor == departure.date() else f":{cursor.isoformat()}"
                result.setdefault(cursor, []).append(
                    ScheduledItem(
                        id=f"{segment.id}{suffix}",
                        kind="flight",
                        name=f"{segment.origin} → {segment.destination}",
                        place_id=None,
                        start=start,
                        end=end,
                        locked=True,
                    )
                )
            cursor += timedelta(days=1)
    for stay in trip.stays:
        for label, raw_time in (("check-in", stay.check_in), ("check-out", stay.check_out)):
            start = _localized(raw_time, zone)
            if trip.start_date <= start.date() <= trip.end_date:
                result.setdefault(start.date(), []).append(
                    ScheduledItem(
                        id=f"{stay.id}:{label}",
                        kind="stay",
                        name=f"{stay.name} {label}",
                        place_id=stay.place_id,
                        start=start,
                        end=start + timedelta(minutes=30),
                        locked=True,
                    )
                )
    return result


def _place_location(places: Dict[str, Place], place_id: Optional[str]) -> Optional[GeoPoint]:
    return places[place_id].location if place_id is not None and place_id in places else None


def _geographic_order(
    values: Sequence[Activity], places: Dict[str, Place], home_place_ids: Sequence[Optional[str]]
) -> List[Activity]:
    """Priority groups ordered with a deterministic nearest-neighbour walk."""

    ordered: List[Activity] = []
    seed = next((_place_location(places, place_id) for place_id in home_place_ids if place_id), None)
    priorities = sorted({activity.priority for activity in values}, reverse=True)
    for priority in priorities:
        remaining = [activity for activity in values if activity.priority == priority]
        current = seed
        while remaining:
            if current is None:
                chosen = min(remaining, key=lambda activity: activity.id)
            else:
                chosen = min(
                    remaining,
                    key=lambda activity: (haversine_km(current, places[activity.place_id].location), activity.id),
                )
            ordered.append(chosen)
            remaining.remove(chosen)
            current = places[chosen.place_id].location
    return ordered


def _validate_anchors(
    day: date,
    items: List[ScheduledItem],
    activities: Dict[str, Activity],
    places: Dict[str, Place],
    matrix: RouteMatrix,
    fallback: HaversineRouteMatrix,
    warnings: List[str],
    conflicts: List[Conflict],
    zone: ZoneInfo,
    day_start: time,
    day_end: time,
    start_place_id: Optional[str],
    end_place_id: Optional[str],
) -> None:
    items.sort(key=lambda item: (item.start, item.id))
    for item in items:
        activity = activities.get(item.id)
        if activity is not None:
            windows = _windows(
                activity,
                day,
                zone,
                day_start,
                day_end,
                restrict_to_day=False,
            )
            if not any(start <= item.start and item.end <= end for start, end in windows):
                conflicts.append(Conflict(code="closed", item_ids=[item.id], on_date=day, message="固定活動不在開放時段內"))
    for previous, current in zip(items, items[1:], strict=False):
        if current.start < previous.end:
            conflicts.append(
                Conflict(code="fixed_overlap", item_ids=[previous.id, current.id], on_date=day, message="固定項目時間重疊；未移動 locked 項目")
            )
            continue
        route = _safe_route(
            matrix,
            fallback,
            _place_location(places, previous.place_id),
            _place_location(places, current.place_id),
            warnings,
        )
        current.travel_from_previous_minutes = route.minutes
        current.travel_estimated = route.estimated
        previous_buffer = activities.get(previous.id).buffer_after_minutes if previous.id in activities else 0
        current_buffer = activities.get(current.id).buffer_before_minutes if current.id in activities else 0
        if previous.end + timedelta(minutes=previous_buffer + route.minutes + current_buffer) > current.start:
            conflicts.append(
                Conflict(
                    code="travel_time_collision",
                    item_ids=[previous.id, current.id],
                    on_date=day,
                    message=f"固定項目間不足 {route.minutes} 分鐘移動與緩衝；未移動 locked 項目",
                )
            )
    if not items:
        return
    day_start_at = _combine(day, day_start, zone)
    day_end_at = _combine(day, day_end, zone)
    first = items[0]
    if first.start >= day_start_at:
        route = _safe_route(
            matrix,
            fallback,
            _place_location(places, start_place_id),
            _place_location(places, first.place_id),
            warnings,
        )
        first.travel_from_previous_minutes = route.minutes
        first.travel_estimated = route.estimated
        before_buffer = activities.get(first.id).buffer_before_minutes if first.id in activities else 0
        if day_start_at + timedelta(minutes=route.minutes + before_buffer) > first.start:
            conflicts.append(
                Conflict(
                    code="travel_time_collision",
                    item_ids=[first.id],
                    on_date=day,
                    message=f"每日起點至首個固定項目不足 {route.minutes} 分鐘移動與緩衝；未移動 locked 項目",
                )
            )
    last = items[-1]
    if last.end <= day_end_at:
        route = _safe_route(
            matrix,
            fallback,
            _place_location(places, last.place_id),
            _place_location(places, end_place_id),
            warnings,
        )
        after_buffer = activities.get(last.id).buffer_after_minutes if last.id in activities else 0
        if last.end + timedelta(minutes=after_buffer + route.minutes) > day_end_at:
            conflicts.append(
                Conflict(
                    code="travel_time_collision",
                    item_ids=[last.id],
                    on_date=day,
                    message=f"末個固定項目後不足 {route.minutes} 分鐘返回每日終點；未移動 locked 項目",
                )
            )


def _insert_activity(
    activity: Activity,
    day: date,
    items: List[ScheduledItem],
    activities: Dict[str, Activity],
    windows: Sequence[Tuple[datetime, datetime]],
    places: Dict[str, Place],
    start_place_id: Optional[str],
    end_place_id: Optional[str],
    matrix: RouteMatrix,
    fallback: HaversineRouteMatrix,
    warnings: List[str],
    day_start_at: datetime,
    day_end_at: datetime,
) -> Optional[ScheduledItem]:
    location = _place_location(places, activity.place_id)
    ordered = sorted(items, key=lambda item: (item.start, item.id))
    for window_start, window_end in windows:
        for gap_index in range(len(ordered) + 1):
            previous = ordered[gap_index - 1] if gap_index else None
            following = ordered[gap_index] if gap_index < len(ordered) else None
            previous_place = previous.place_id if previous else start_place_id
            following_place = following.place_id if following else end_place_id
            before = _safe_route(matrix, fallback, _place_location(places, previous_place), location, warnings)
            after = _safe_route(matrix, fallback, location, _place_location(places, following_place), warnings)
            earliest = window_start
            previous_buffer = activities.get(previous.id).buffer_after_minutes if previous is not None and previous.id in activities else 0
            following_buffer = activities.get(following.id).buffer_before_minutes if following is not None and following.id in activities else 0
            if previous is not None:
                earliest = max(earliest, previous.end + timedelta(minutes=previous_buffer + before.minutes))
            else:
                earliest = max(earliest, day_start_at + timedelta(minutes=before.minutes))
            earliest += timedelta(minutes=activity.buffer_before_minutes)
            if activity.latest_start is not None and earliest.time() > activity.latest_start:
                continue
            end = earliest + timedelta(minutes=activity.duration_minutes)
            required_end = end + timedelta(minutes=activity.buffer_after_minutes + after.minutes + following_buffer)
            gap_end = following.start if following is not None else day_end_at
            if end <= window_end and required_end <= gap_end:
                return ScheduledItem(
                    id=activity.id,
                    kind="activity",
                    name=activity.name,
                    place_id=activity.place_id,
                    start=earliest,
                    end=end,
                    locked=False,
                    travel_from_previous_minutes=before.minutes,
                    travel_estimated=before.estimated,
                )
    return None


def schedule_trip(
    trip: Trip,
    route_matrix: Optional[RouteMatrix] = None,
    *,
    day_start: time = time(9, 0),
    day_end: time = time(18, 0),
) -> PlanResult:
    """Create a reproducible plan; never moves fixed/locked inputs."""

    if day_start >= day_end:
        raise ValueError("day_start must be before day_end")
    zone = _timezone(trip.timezone)
    fallback = HaversineRouteMatrix()
    matrix = route_matrix or fallback
    places = {place.id: place for place in trip.places}
    activities = {activity.id: activity for activity in trip.activities}
    conflicts: List[Conflict] = []
    warnings: List[str] = []
    explanations: List[Explanation] = []
    anchored = _anchor_items(trip, zone, conflicts)
    days: Dict[date, List[ScheduledItem]] = {}
    cursor = trip.start_date
    while cursor <= trip.end_date:
        items = list(anchored.get(cursor, []))
        days[cursor] = items
        cursor += timedelta(days=1)

    fixed_ids = {item.id for items in days.values() for item in items if item.kind == "activity"}
    flexible = [activity for activity in trip.activities if activity.id not in fixed_ids]
    explicit_day_places = {item.on_date: (item.start_place_id, item.end_place_id) for item in trip.days}
    day_places: Dict[date, Tuple[Optional[str], Optional[str]]] = {}
    for day in days:
        fallback_home = _stay_place(trip, day, zone)
        explicit_start, explicit_end = explicit_day_places.get(day, (None, None))
        day_places[day] = (explicit_start or fallback_home, explicit_end or fallback_home)
    for day, items in days.items():
        start_place_id, end_place_id = day_places[day]
        _validate_anchors(
            day,
            items,
            activities,
            places,
            matrix,
            fallback,
            warnings,
            conflicts,
            zone,
            day_start,
            day_end,
            start_place_id,
            end_place_id,
        )
    flexible = _geographic_order(flexible, places, [value[0] for value in day_places.values()])
    unscheduled: List[str] = []
    for activity in flexible:
        placed = False
        had_open_day = False
        for day, items in days.items():
            windows = _windows(activity, day, zone, day_start, day_end)
            if not windows:
                continue
            had_open_day = True
            item = _insert_activity(
                activity,
                day,
                items,
                activities,
                windows,
                places,
                day_places[day][0],
                day_places[day][1],
                matrix,
                fallback,
                warnings,
                _combine(day, day_start, zone),
                _combine(day, day_end, zone),
            )
            if item is not None:
                items.append(item)
                items.sort(key=lambda value: (value.start, value.id))
                explanations.append(
                    Explanation(item_id=activity.id, code="scheduled", message=f"依 priority、開放時段與移動時間排入 {day.isoformat()}")
                )
                placed = True
                break
        if not placed:
            unscheduled.append(activity.id)
            code = "window_too_short" if had_open_day else "closed"
            message = "所有可用時窗扣除活動、緩衝與移動時間後皆不足" if had_open_day else "旅程日期內沒有開放時段"
            conflicts.append(Conflict(code=code, item_ids=[activity.id], message=message))
            explanations.append(Explanation(item_id=activity.id, code=code, message=message))

    return PlanResult(
        trip_id=trip.id,
        days=[PlanDay(date=day, items=items) for day, items in days.items()],
        unscheduled_activity_ids=unscheduled,
        conflicts=conflicts,
        explanations=explanations,
        warnings=warnings,
    )

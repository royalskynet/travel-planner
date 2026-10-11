"""V2 application services joining domain, planning, storage and exporters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .core import validate_input
from .domain import Trip, migrate_v1
from .exporters import (
    export_geojson,
    export_ics,
    export_json,
    export_kml,
    export_markdown,
)
from .planning import PlanResult, schedule_trip
from .storage import RevisionRecord, SQLiteTripRepository


def parse_trip(data: dict[str, Any], *, trip_id: str | None = None) -> Trip:
    """Parse V2 input or migrate a validated V1 document."""

    if data.get("schema_version") == 2:
        trip = Trip.model_validate(data)
        return trip if trip_id is None else trip.model_copy(update={"id": trip_id})
    validate_input(data)
    return migrate_v1(data, trip_id=trip_id or "trip-v1")


def load_trip(path: Path, *, trip_id: str | None = None) -> Trip:
    return parse_trip(json.loads(path.read_text(encoding="utf-8")), trip_id=trip_id)


def _source_details(trip: Trip, source_ids: list[str]) -> list[dict[str, Any]]:
    sources = {source.id: source for source in trip.sources}
    return [sources[source_id].model_dump(mode="json") for source_id in source_ids if source_id in sources]


def build_output(trip: Trip, plan: PlanResult) -> dict[str, Any]:
    """Enrich the pure plan with coordinates, provenance and budget facts."""

    places = {place.id: place for place in trip.places}
    activities = {activity.id: activity for activity in trip.activities}
    reservations = {item.id: item for item in trip.reservations}
    days: list[dict[str, Any]] = []
    for day in plan.days:
        items: list[dict[str, Any]] = []
        for scheduled in day.items:
            activity = activities.get(scheduled.id)
            reservation = reservations.get(scheduled.id)
            source_ids = activity.source_ids if activity else (reservation.source_ids if reservation else [])
            place = places.get(scheduled.place_id) if scheduled.place_id else None
            item = scheduled.model_dump(mode="json")
            item["start_at"] = item.pop("start")
            item["end_at"] = item.pop("end")
            item["duration_minutes"] = int((scheduled.end - scheduled.start).total_seconds() // 60)
            item["estimated"] = scheduled.travel_estimated
            item_sources = _source_details(trip, source_ids)
            if item_sources:
                item["sources"] = item_sources
                if item_sources[0].get("url"):
                    item["source_url"] = item_sources[0]["url"]
            if place is not None:
                item.update(
                    {
                        "place_name": place.name,
                        "latitude": place.location.latitude,
                        "longitude": place.location.longitude,
                    }
                )
            items.append(item)
        days.append({"date": day.date.isoformat(), "items": items})

    totals: dict[str, float] = {}
    for expense in trip.expenses:
        totals[expense.currency] = totals.get(expense.currency, 0.0) + expense.amount
    primary_total = totals.get(trip.currency, 0.0)
    remaining = None if trip.budget is None else trip.budget - primary_total
    warnings = list(plan.warnings)
    if any(currency != trip.currency for currency in totals):
        warnings.append("預算含未換算幣別；各幣別分列，未直接相加。")
    return {
        "schema_version": 2,
        "id": trip.id,
        "title": trip.title,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "timezone": trip.timezone,
        "currency": trip.currency,
        "days": days,
        "flight_segments": [item.model_dump(mode="json") for item in trip.flight_segments],
        "travel_legs": [item.model_dump(mode="json") for item in trip.travel_legs],
        "stays": [item.model_dump(mode="json") for item in trip.stays],
        "reservations": [item.model_dump(mode="json") for item in trip.reservations],
        "expenses": [item.model_dump(mode="json") for item in trip.expenses],
        "checklist": [item.model_dump(mode="json") for item in trip.checklist],
        "sources": [item.model_dump(mode="json") for item in trip.sources],
        "budget_summary": {
            "budget": trip.budget,
            "primary_currency": trip.currency,
            "totals_by_currency": totals,
            "remaining_primary_currency": remaining,
        },
        "unscheduled_activity_ids": plan.unscheduled_activity_ids,
        "conflicts": [item.model_dump(mode="json") for item in plan.conflicts],
        "explanations": [item.model_dump(mode="json") for item in plan.explanations],
        "warnings": warnings,
        "disclaimer": "價格、班次與開放時間需重查；未代訂、未付款。",
    }


EXPORTERS: dict[str, Callable[[Any], str]] = {
    "json": export_json,
    "markdown": export_markdown,
    "ics": export_ics,
    "geojson": export_geojson,
    "kml": export_kml,
}


def write_outputs(payload: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "json": "plan.json",
        "markdown": "plan.md",
        "ics": "plan.ics",
        "geojson": "plan.geojson",
        "kml": "plan.kml",
    }
    paths: dict[str, Path] = {}
    for output_format, filename in names.items():
        path = output_dir / filename
        path.write_text(EXPORTERS[output_format](payload), encoding="utf-8")
        paths[output_format] = path
    return paths


def create_trip(input_path: Path, database: Path, *, trip_id: str | None = None) -> tuple[Trip, int]:
    trip = load_trip(input_path, trip_id=trip_id)
    revision = SQLiteTripRepository(database).save(trip)
    return trip, revision


def plan_trip(trip_id: str, database: Path, output_dir: Path) -> tuple[dict[str, Any], int, dict[str, Path]]:
    repository = SQLiteTripRepository(database)
    record = repository.get(trip_id)
    plan = schedule_trip(record.trip)
    payload = build_output(record.trip, plan)
    revision = repository.save(record.trip, plan=payload)
    return payload, revision, write_outputs(payload, output_dir)


def latest_planned_trip(trip_id: str, database: Path) -> RevisionRecord:
    return SQLiteTripRepository(database).get_latest_planned(trip_id)


def export_saved_trip(trip_id: str, database: Path, output_format: str, output: Path) -> Path:
    record = latest_planned_trip(trip_id, database)
    exporter = EXPORTERS[output_format]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(exporter(record.plan), encoding="utf-8")
    return output

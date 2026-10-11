"""Normalized V2 domain contracts.

The models contain facts and user intent only. Provider payloads and generated
schedule output belong at adapter/planning boundaries.
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GeoPoint(DomainModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SourceSnapshot(DomainModel):
    id: str
    url: Optional[HttpUrl] = None
    provider: str
    checked_at: AwareDatetime
    status: Literal["verified", "estimated", "stale", "unavailable"] = "verified"
    freshness_seconds: Optional[int] = Field(default=None, ge=0)
    facts: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_verified_source(self) -> "SourceSnapshot":
        if self.status == "verified" and self.url is None:
            raise ValueError("verified source requires url")
        return self


class Place(DomainModel):
    id: str
    name: str
    location: GeoPoint
    address: Optional[str] = None
    timezone: Optional[str] = None
    external_ids: Dict[str, str] = Field(default_factory=dict)
    source_ids: List[str] = Field(default_factory=list)


class Day(DomainModel):
    on_date: date
    start_place_id: Optional[str] = None
    end_place_id: Optional[str] = None


class TravelLeg(DomainModel):
    id: str
    origin_place_id: str
    destination_place_id: str
    mode: Literal["walking", "cycling", "driving", "transit", "flight", "train", "other"]
    duration_minutes: int = Field(ge=0)
    distance_km: Optional[float] = Field(default=None, ge=0)
    provider: str
    estimated: bool = False
    source_id: Optional[str] = None


class OpeningWindow(DomainModel):
    """A weekly or date-specific half-open availability interval."""

    start: time
    end: time
    weekday: Optional[int] = Field(default=None, ge=1, le=7)
    on_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_window(self) -> "OpeningWindow":
        if self.weekday is None and self.on_date is None:
            raise ValueError("opening window requires weekday or on_date")
        if self.start >= self.end:
            raise ValueError("opening window start must be before end")
        return self


class FlightSegment(DomainModel):
    id: str
    origin: str = Field(pattern=r"^[A-Z]{3}$")
    destination: str = Field(pattern=r"^[A-Z]{3}$")
    departure: AwareDatetime
    arrival: Optional[AwareDatetime] = None
    carrier: Optional[str] = None
    flight_number: Optional[str] = None
    source_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_times(self) -> "FlightSegment":
        if self.arrival is not None:
            if self.arrival <= self.departure:
                raise ValueError("flight arrival must be after departure")
        return self


class Activity(DomainModel):
    id: str
    name: str
    place_id: str
    duration_minutes: int = Field(gt=0)
    opening_windows: List[OpeningWindow] = Field(default_factory=list)
    fixed_start: Optional[AwareDatetime] = None
    scheduled_start: Optional[AwareDatetime] = None
    earliest_start: Optional[time] = None
    latest_start: Optional[time] = None
    locked: bool = False
    buffer_before_minutes: int = Field(default=0, ge=0)
    buffer_after_minutes: int = Field(default=0, ge=0)
    priority: int = Field(default=50, ge=0, le=100)
    tags: List[str] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lock(self) -> "Activity":
        if self.locked and self.fixed_start is None and self.scheduled_start is None:
            raise ValueError("locked activity requires fixed_start or scheduled_start")
        return self


class Stay(DomainModel):
    id: str
    name: str
    place_id: str
    check_in: AwareDatetime
    check_out: AwareDatetime
    confirmation_code: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self) -> "Stay":
        if self.check_out <= self.check_in:
            raise ValueError("stay check_out must be after check_in")
        return self


class Reservation(DomainModel):
    id: str
    kind: Literal["flight", "train", "stay", "restaurant", "activity", "other"]
    name: str
    starts_at: AwareDatetime
    ends_at: Optional[AwareDatetime] = None
    place_id: Optional[str] = None
    confirmation_code: Optional[str] = None
    status: Literal["planned", "held", "confirmed", "cancelled"] = "planned"
    source_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_times(self) -> "Reservation":
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("reservation ends_at must be after starts_at")
        return self


class ExpenseStatus(str, Enum):
    PLANNED = "planned"
    QUOTED = "quoted"
    PAID = "paid"


class Expense(DomainModel):
    id: str
    category: Literal["transport", "stay", "activity", "food", "insurance", "shopping", "other"]
    amount: float = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: ExpenseStatus = ExpenseStatus.PLANNED
    incurred_on: Optional[date] = None
    description: Optional[str] = None
    source_id: Optional[str] = None


class ChecklistItem(DomainModel):
    id: str
    text: str
    category: Literal["packing", "booking", "document", "recheck", "other"] = "other"
    due_at: Optional[datetime] = None
    completed: bool = False


class Trip(DomainModel):
    schema_version: Literal[2] = 2
    id: str
    title: str
    start_date: date
    end_date: date
    timezone: str = "UTC"
    travellers: int = Field(default=1, gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    budget: Optional[float] = Field(default=None, ge=0)
    interests: List[str] = Field(default_factory=list)
    places: List[Place] = Field(default_factory=list)
    days: List[Day] = Field(default_factory=list)
    flight_segments: List[FlightSegment] = Field(default_factory=list)
    travel_legs: List[TravelLeg] = Field(default_factory=list)
    activities: List[Activity] = Field(default_factory=list)
    stays: List[Stay] = Field(default_factory=list)
    reservations: List[Reservation] = Field(default_factory=list)
    expenses: List[Expense] = Field(default_factory=list)
    checklist: List[ChecklistItem] = Field(default_factory=list)
    sources: List[SourceSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trip(self) -> "Trip":
        if self.end_date < self.start_date:
            raise ValueError("trip end_date must not be before start_date")
        place_ids = [place.id for place in self.places]
        if len(place_ids) != len(set(place_ids)):
            raise ValueError("place ids must be unique")
        known_places = set(place_ids)
        references = [activity.place_id for activity in self.activities]
        references += [place_id for day in self.days for place_id in (day.start_place_id, day.end_place_id) if place_id]
        references += [place_id for leg in self.travel_legs for place_id in (leg.origin_place_id, leg.destination_place_id)]
        references += [stay.place_id for stay in self.stays]
        references += [item.place_id for item in self.reservations if item.place_id]
        missing = sorted(set(references) - known_places)
        if missing:
            raise ValueError("unknown place references: " + ", ".join(missing))
        for field_name in ("flight_segments", "travel_legs", "activities", "stays", "reservations", "expenses", "checklist", "sources"):
            ids = [item.id for item in getattr(self, field_name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{field_name} ids must be unique")
        known_sources = {source.id for source in self.sources}
        source_references = [source_id for place in self.places for source_id in place.source_ids]
        source_references += [segment.source_id for segment in self.flight_segments if segment.source_id]
        source_references += [leg.source_id for leg in self.travel_legs if leg.source_id]
        source_references += [source_id for activity in self.activities for source_id in activity.source_ids]
        source_references += [source_id for stay in self.stays for source_id in stay.source_ids]
        source_references += [source_id for reservation in self.reservations for source_id in reservation.source_ids]
        source_references += [expense.source_id for expense in self.expenses if expense.source_id]
        missing_sources = sorted(set(source_references) - known_sources)
        if missing_sources:
            raise ValueError("unknown source references: " + ", ".join(missing_sources))
        return self

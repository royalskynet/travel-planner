import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.domain import (
    Activity,
    FlightSegment,
    Reservation,
    SourceSnapshot,
    Stay,
    Trip,
    migrate_v1,
)

FIXTURE = {
    "origin": "TPE",
    "destination": "KIX",
    "start_date": "2026-10-01",
    "end_date": "2026-10-02",
    "travellers": 2,
    "budget": 5000,
    "currency": "TWD",
    "interests": ["food"],
    "activities": [
        {
            "name": "市場",
            "duration_minutes": 90,
            "cost": 100,
            "latitude": 35,
            "longitude": 135,
            "open_weekdays": [4],
            "interests": ["food"],
            "source_url": "https://www.kuromon.com/en/",
            "checked_at": "2026-09-19T00:00:00Z",
        }
    ],
}


class DomainTests(unittest.TestCase):
    def test_v1_migration_preserves_route_activity_cost_and_source(self):
        trip = migrate_v1(FIXTURE, trip_id="osaka")
        self.assertEqual(trip.id, "osaka")
        self.assertEqual([(leg.origin, leg.destination) for leg in trip.flight_segments], [("TPE", "KIX")])
        self.assertEqual(trip.activities[0].name, "市場")
        self.assertEqual(trip.expenses[0].amount, 100)
        self.assertEqual(str(trip.sources[0].url), "https://www.kuromon.com/en/")
        self.assertEqual(trip.sources[-1].status, "estimated")
        self.assertIsNone(trip.sources[-1].url)

    def test_v1_migration_is_deterministic(self):
        first = migrate_v1(FIXTURE).model_dump(mode="json")
        second = migrate_v1(FIXTURE).model_dump(mode="json")
        self.assertEqual(first, second)

    def test_multi_segment_round_trip(self):
        trip = migrate_v1(FIXTURE)
        trip.flight_segments.extend(
            [
                FlightSegment(id="segment-2", origin="KIX", destination="CTS", departure="2026-10-02T09:00:00+09:00"),
                FlightSegment(id="segment-3", origin="CTS", destination="TPE", departure="2026-10-03T09:00:00+09:00"),
            ]
        )
        restored = Trip.model_validate_json(trip.model_dump_json())
        self.assertEqual([(leg.origin, leg.destination) for leg in restored.flight_segments], [("TPE", "KIX"), ("KIX", "CTS"), ("CTS", "TPE")])

    def test_verified_source_requires_real_url(self):
        with self.assertRaises(ValidationError):
            SourceSnapshot(id="s", provider="manual", checked_at="2026-01-01T00:00:00Z", status="verified")

    def test_flight_rejects_naive_datetimes(self):
        for departure, arrival in (
            ("2026-01-01T09:00:00", "2026-01-01T12:00:00+08:00"),
            ("2026-01-01T09:00:00+08:00", "2026-01-01T12:00:00"),
        ):
            with self.subTest(departure=departure, arrival=arrival):
                with self.assertRaises(ValidationError):
                    FlightSegment(id="s", origin="TPE", destination="KIX", departure=departure, arrival=arrival)

    def test_external_and_anchor_times_require_timezone(self):
        constructors = [
            lambda: SourceSnapshot(id="s", url="https://example.org", provider="x", checked_at="2026-01-01T00:00:00"),
            lambda: Activity(id="a", name="A", place_id="p", duration_minutes=30, fixed_start="2026-01-01T09:00:00"),
            lambda: Activity(id="a", name="A", place_id="p", duration_minutes=30, scheduled_start="2026-01-01T09:00:00"),
            lambda: Stay(id="s", name="S", place_id="p", check_in="2026-01-01T15:00:00", check_out="2026-01-02T11:00:00+08:00"),
            lambda: Stay(id="s", name="S", place_id="p", check_in="2026-01-01T15:00:00+08:00", check_out="2026-01-02T11:00:00"),
            lambda: Reservation(id="r", kind="restaurant", name="R", starts_at="2026-01-01T12:00:00"),
            lambda: Reservation(id="r", kind="restaurant", name="R", starts_at="2026-01-01T12:00:00+08:00", ends_at="2026-01-01T13:00:00"),
        ]
        for constructor in constructors:
            with self.subTest(constructor=constructor):
                with self.assertRaises(ValidationError):
                    constructor()


if __name__ == "__main__":
    unittest.main()

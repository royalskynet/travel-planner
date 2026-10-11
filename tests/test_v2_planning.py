import sys
import unittest
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.domain import (
    Activity,
    Day,
    FlightSegment,
    GeoPoint,
    OpeningWindow,
    Place,
    Reservation,
    Stay,
    Trip,
)
from travel_assistant.planning import RouteEstimate, schedule_trip


class FixedMatrix:
    def __init__(self, minutes=30):
        self.minutes = minutes

    def estimate(self, origin, destination, *, mode="walking"):
        return RouteEstimate(minutes=self.minutes, distance_km=1, provider="fixture", estimated=False)


def make_trip(activities, reservations=None):
    places = [
        Place(id="a", name="A", location=GeoPoint(latitude=25.0, longitude=121.5)),
        Place(id="b", name="B", location=GeoPoint(latitude=25.01, longitude=121.51)),
        Place(id="c", name="C", location=GeoPoint(latitude=25.02, longitude=121.52)),
    ]
    return Trip(
        id="trip",
        title="Trip",
        start_date="2026-10-01",
        end_date="2026-10-01",
        timezone="Asia/Taipei",
        places=places,
        activities=activities,
        reservations=reservations or [],
    )


class PlanningTests(unittest.TestCase):
    def test_fixed_items_never_move_and_conflict_is_machine_readable(self):
        trip = make_trip(
            [
                Activity(id="one", name="One", place_id="a", duration_minutes=60, fixed_start="2026-10-01T10:00:00+08:00", locked=True),
                Activity(id="two", name="Two", place_id="b", duration_minutes=60, fixed_start="2026-10-01T10:30:00+08:00", locked=True),
            ]
        )
        result = schedule_trip(trip, FixedMatrix())
        self.assertEqual([item.start.isoformat() for item in result.days[0].items], ["2026-10-01T10:00:00+08:00", "2026-10-01T10:30:00+08:00"])
        self.assertIn("fixed_overlap", [conflict.code for conflict in result.conflicts])

    def test_travel_time_is_included_before_fixed_anchor(self):
        trip = make_trip(
            [Activity(id="visit", name="Visit", place_id="a", duration_minutes=30, opening_windows=[OpeningWindow(on_date="2026-10-01", start="09:00", end="12:00")])],
            [Reservation(id="lunch", kind="restaurant", name="Lunch", starts_at="2026-10-01T10:00:00+08:00", ends_at="2026-10-01T11:00:00+08:00", place_id="b")],
        )
        result = schedule_trip(trip, FixedMatrix(30))
        visit = next(item for item in result.days[0].items if item.id == "visit")
        self.assertEqual(visit.start.time(), time(9, 0))
        self.assertEqual(visit.end.time(), time(9, 30))
        self.assertEqual(visit.travel_from_previous_minutes, 0)

    def test_impossible_window_produces_conflict_instead_of_dropping(self):
        trip = make_trip(
            [Activity(id="too-long", name="Too long", place_id="a", duration_minutes=90, opening_windows=[OpeningWindow(on_date="2026-10-01", start="09:00", end="10:00")])]
        )
        result = schedule_trip(trip, FixedMatrix())
        self.assertEqual(result.unscheduled_activity_ids, ["too-long"])
        self.assertEqual(result.conflicts[0].code, "window_too_short")
        self.assertTrue(result.explanations)

    def test_adjacent_activity_buffer_can_make_slot_impossible(self):
        without_buffer = make_trip(
            [
                Activity(id="first", name="First", place_id="a", duration_minutes=30, fixed_start="2026-10-01T09:00:00+08:00"),
                Activity(id="candidate", name="Candidate", place_id="a", duration_minutes=30, opening_windows=[OpeningWindow(on_date="2026-10-01", start="09:30", end="10:00")]),
            ]
        )
        self.assertNotIn("candidate", schedule_trip(without_buffer, FixedMatrix(0)).unscheduled_activity_ids)

        with_buffer = without_buffer.model_copy(deep=True)
        with_buffer.activities[0].buffer_after_minutes = 15
        result = schedule_trip(with_buffer, FixedMatrix(0))
        self.assertIn("candidate", result.unscheduled_activity_ids)
        self.assertIn("window_too_short", [conflict.code for conflict in result.conflicts])

    def test_closed_activity_produces_conflict(self):
        trip = make_trip(
            [Activity(id="closed", name="Closed", place_id="a", duration_minutes=30, opening_windows=[OpeningWindow(weekday=5, start="09:00", end="10:00")])]
        )
        result = schedule_trip(trip)
        self.assertEqual(result.conflicts[0].code, "closed")

    def test_route_failure_falls_back_with_warning(self):
        class BrokenMatrix:
            def estimate(self, origin, destination, *, mode="walking"):
                raise TimeoutError("offline")

        trip = make_trip(
            [
                Activity(id="one", name="One", place_id="a", duration_minutes=30, fixed_start="2026-10-01T09:00:00+08:00"),
                Activity(id="two", name="Two", place_id="b", duration_minutes=30, fixed_start="2026-10-01T10:00:00+08:00"),
            ]
        )
        result = schedule_trip(trip, BrokenMatrix())
        self.assertIn("used haversine", result.warnings[0])

    def test_same_priority_uses_nearest_neighbour_order(self):
        trip = make_trip(
            [
                Activity(id="aa-seed", name="Seed", place_id="a", duration_minutes=30),
                Activity(id="zz-near", name="Near", place_id="b", duration_minutes=30),
                Activity(id="mm-far", name="Far", place_id="c", duration_minutes=30),
            ]
        )
        result = schedule_trip(trip, FixedMatrix(0))
        self.assertEqual([item.id for item in result.days[0].items], ["aa-seed", "zz-near", "mm-far"])

    def test_day_boundary_travel_does_not_delay_opening_time(self):
        trip = make_trip(
            [Activity(id="visit", name="Visit", place_id="b", duration_minutes=30, opening_windows=[OpeningWindow(on_date="2026-10-01", start="11:00", end="12:00")])]
        )
        trip.days = [Day(on_date="2026-10-01", start_place_id="a", end_place_id="a")]
        result = schedule_trip(trip, FixedMatrix(30))
        visit = result.days[0].items[0]
        self.assertEqual(visit.start.time(), time(11, 0))
        self.assertEqual(visit.travel_from_previous_minutes, 30)

    def test_return_travel_uses_day_end_not_activity_closing(self):
        trip = make_trip(
            [Activity(id="visit", name="Visit", place_id="b", duration_minutes=30, opening_windows=[OpeningWindow(on_date="2026-10-01", start="16:30", end="17:00")])]
        )
        trip.days = [Day(on_date="2026-10-01", start_place_id="a", end_place_id="a")]
        result = schedule_trip(trip, FixedMatrix(30))
        self.assertEqual(result.unscheduled_activity_ids, [])
        self.assertEqual(result.days[0].items[0].end.time(), time(17, 0))

    def test_fixed_anchor_checks_day_start_travel_and_records_it(self):
        trip = make_trip(
            [Activity(id="fixed", name="Fixed", place_id="b", duration_minutes=30, fixed_start="2026-10-01T09:15:00+08:00", locked=True)]
        )
        trip.days = [Day(on_date="2026-10-01", start_place_id="a", end_place_id="a")]
        result = schedule_trip(trip, FixedMatrix(30))
        self.assertEqual(result.days[0].items[0].travel_from_previous_minutes, 30)
        self.assertIn("travel_time_collision", [conflict.code for conflict in result.conflicts])

    def test_fixed_activity_before_default_day_start_can_still_be_open(self):
        trip = make_trip(
            [
                Activity(
                    id="early",
                    name="Early",
                    place_id="a",
                    duration_minutes=30,
                    fixed_start="2026-10-01T08:00:00+08:00",
                    opening_windows=[
                        OpeningWindow(
                            on_date="2026-10-01", start="06:00", end="12:00"
                        )
                    ],
                    locked=True,
                )
            ]
        )
        result = schedule_trip(trip, FixedMatrix(0))
        self.assertNotIn("closed", [conflict.code for conflict in result.conflicts])

    def test_cancelled_reservation_is_not_an_anchor(self):
        trip = make_trip(
            [],
            [Reservation(id="cancelled", kind="restaurant", name="No meal", starts_at="2026-10-01T12:00:00+08:00", status="cancelled")],
        )
        self.assertEqual(schedule_trip(trip).days[0].items, [])

    def test_flight_arrival_blocks_activities_until_arrival(self):
        trip = make_trip([Activity(id="visit", name="Visit", place_id="a", duration_minutes=30)])
        trip.flight_segments = [
            FlightSegment(
                id="inbound",
                origin="TPE",
                destination="KIX",
                departure="2026-10-01T07:00:00+08:00",
                arrival="2026-10-01T11:00:00+08:00",
            )
        ]
        result = schedule_trip(trip, FixedMatrix(0))
        visit = next(item for item in result.days[0].items if item.id == "visit")
        self.assertEqual(visit.start.time(), time(11, 0))
        self.assertEqual(result.days[0].items[0].kind, "flight")

    def test_stay_check_in_and_out_are_locked_anchors(self):
        trip = make_trip([])
        trip.stays = [
            Stay(
                id="hotel",
                name="Hotel",
                place_id="a",
                check_in="2026-10-01T15:00:00+08:00",
                check_out="2026-10-01T17:00:00+08:00",
            )
        ]
        result = schedule_trip(trip, FixedMatrix(0))
        self.assertEqual([item.kind for item in result.days[0].items], ["stay", "stay"])
        self.assertTrue(all(item.locked for item in result.days[0].items))

    def test_explicit_day_places_override_stay_and_stay_is_fallback(self):
        class OriginMatrix:
            def estimate(self, origin, destination, *, mode="walking"):
                minutes = 40 if origin.latitude == 25.02 else 10
                return RouteEstimate(minutes=minutes, distance_km=1, provider="fixture", estimated=False)

        trip = make_trip([Activity(id="visit", name="Visit", place_id="b", duration_minutes=30)])
        trip.stays = [
            Stay(
                id="hotel",
                name="Hotel",
                place_id="a",
                check_in="2026-10-01T15:00:00+08:00",
                check_out="2026-10-02T11:00:00+08:00",
            )
        ]
        trip.days = [Day(on_date="2026-10-01", start_place_id="c", end_place_id="c")]
        explicit = schedule_trip(trip, OriginMatrix())
        explicit_visit = next(item for item in explicit.days[0].items if item.id == "visit")
        self.assertEqual(explicit_visit.start.time(), time(9, 40))

        fallback_trip = trip.model_copy(deep=True)
        fallback_trip.days = []
        fallback = schedule_trip(fallback_trip, OriginMatrix())
        fallback_visit = next(item for item in fallback.days[0].items if item.id == "visit")
        self.assertEqual(fallback_visit.start.time(), time(9, 10))


if __name__ == "__main__":
    unittest.main()

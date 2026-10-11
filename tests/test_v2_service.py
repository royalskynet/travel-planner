import json
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.v2 import create_trip, latest_planned_trip, parse_trip, plan_trip

V1 = {
    "origin": "TPE",
    "destination": "KIX",
    "start_date": "2026-10-01",
    "end_date": "2026-10-02",
    "travellers": 1,
    "budget": 5000,
    "currency": "TWD",
    "pace": "moderate",
    "interests": ["food"],
    "activities": [
        {
            "name": "市場",
            "duration_minutes": 90,
            "cost": 100,
            "latitude": 34.6653,
            "longitude": 135.5067,
            "open_weekdays": [4],
            "interests": ["food"],
            "source_url": "https://www.kuromon.com/en/",
            "checked_at": "2026-09-19T00:00:00Z",
        }
    ],
}


class V2ServiceTests(unittest.TestCase):
    def test_v1_create_plan_store_and_export_all_formats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.json"
            source.write_text(json.dumps(V1, ensure_ascii=False), encoding="utf-8")
            trip, revision = create_trip(source, root / "trips.db", trip_id="osaka")
            self.assertEqual((trip.id, revision), ("osaka", 1))
            payload, revision, paths = plan_trip("osaka", root / "trips.db", root / "output")
            self.assertEqual(revision, 2)
            self.assertEqual(set(paths), {"json", "markdown", "ics", "geojson", "kml"})
            self.assertTrue(all(path.is_file() for path in paths.values()))
            self.assertEqual(json.loads(paths["json"].read_text())["id"], "osaka")
            self.assertEqual(len(json.loads(paths["geojson"].read_text())["features"]), 1)
            self.assertEqual(latest_planned_trip("osaka", root / "trips.db").revision, 2)
            self.assertEqual(payload["budget_summary"]["remaining_primary_currency"], 4900)
            self.assertEqual(payload["sources"][0]["provider"], "v1-input")
            self.assertEqual(payload["days"][0]["items"][0]["sources"][0]["status"], "verified")
            self.assertIn("checked_at", payload["days"][0]["items"][0]["sources"][0])
            self.assertEqual(payload["travel_legs"], [])
            _, unplanned_revision = create_trip(source, root / "trips.db", trip_id="osaka")
            self.assertEqual(unplanned_revision, 3)
            self.assertEqual(latest_planned_trip("osaka", root / "trips.db").revision, 2)

    def test_v2_extra_fields_fail_loud(self):
        with self.assertRaises(ValidationError):
            parse_trip(
                {
                    "schema_version": 2,
                    "id": "x",
                    "title": "X",
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-01",
                    "unknown": True,
                }
            )


if __name__ == "__main__":
    unittest.main()

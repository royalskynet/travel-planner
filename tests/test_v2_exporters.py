import json
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from icalendar import Calendar

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.exporters import (
    export_geojson,
    export_ics,
    export_json,
    export_kml,
    export_markdown,
)

TRIP = {
    "id": "trip-1",
    "name": "大阪行",
    "api_key": "must-not-leak",
    "warnings": ["價格需重新查證"],
    "days": [
        {
            "date": "2026-10-01",
            "items": [
                {
                    "name": "黑門市場",
                    "start_at": "2026-10-01T09:00:00+09:00",
                    "duration_minutes": 90,
                    "latitude": 34.6653,
                    "longitude": 135.5067,
                    "source_url": "https://www.kuromon.com/en/",
                }
            ],
        },
        {"date": "2026-10-02", "items": [{"name": "自由活動"}]},
    ],
}


class ExporterTests(unittest.TestCase):
    def test_json_round_trip_and_secret_redaction(self):
        parsed = json.loads(export_json(TRIP))
        self.assertEqual(parsed["name"], "大阪行")
        self.assertNotIn("api_key", parsed)
        self.assertNotIn("must-not-leak", export_json(TRIP))

    def test_markdown_contains_days_sources_and_warning(self):
        output = export_markdown(TRIP)
        self.assertIn("# 大阪行", output)
        self.assertIn("2026-10-01", output)
        self.assertIn("https://www.kuromon.com/en/", output)
        self.assertIn("價格需重新查證", output)

    def test_geojson_round_trip(self):
        parsed = json.loads(export_geojson(TRIP))
        self.assertEqual(parsed["type"], "FeatureCollection")
        self.assertEqual(
            parsed["features"][0]["geometry"]["coordinates"], [135.5067, 34.6653]
        )

    def test_kml_round_trip(self):
        root = ET.fromstring(export_kml(TRIP))
        namespace = {"k": "http://www.opengis.net/kml/2.2"}
        self.assertEqual(root.tag, "{http://www.opengis.net/kml/2.2}kml")
        self.assertEqual(
            root.findtext(".//k:coordinates", namespaces=namespace),
            "135.5067,34.6653,0",
        )

    def test_ics_basic_parser_round_trip(self):
        output = export_ics(TRIP)
        self.assertEqual(output, export_ics(TRIP))
        self.assertTrue(output.endswith("\r\n"))
        calendar = Calendar.from_ical(output)
        events = [
            component for component in calendar.walk() if component.name == "VEVENT"
        ]
        self.assertEqual(len(events), 2)
        self.assertEqual(
            events[0].decoded("dtstart").isoformat(), "2026-10-01T00:00:00+00:00"
        )
        self.assertEqual(events[1].decoded("dtstart").isoformat(), "2026-10-02")
        self.assertEqual(
            events[0].decoded("dtstamp").isoformat(), "1970-01-01T00:00:00+00:00"
        )


if __name__ == "__main__":
    unittest.main()

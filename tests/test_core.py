import json
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from travel_assistant.cli import build_plan, markdown
from travel_assistant.core import ValidationError, schedule, validate_input
from travel_assistant.providers import DuffelFlightProvider, MockFlightProvider, SkyscannerFlightProvider
from travel_assistant.weather import get_weather

BASE = {"origin": "TPE", "destination": "KIX", "start_date": "2026-10-01", "end_date": "2026-10-02", "travellers": 1, "budget": 5000, "currency": "TWD", "pace": "moderate", "interests": ["food"], "activities": [{"name": "市場", "duration_minutes": 90, "cost": 100, "latitude": 35, "longitude": 135, "open_weekdays": [4], "interests": ["food"], "source_url": "https://www.kuromon.com/en/", "checked_at": "2026-09-19T00:00:00Z"}]}


class Response:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return json.dumps(self.body).encode()


class Tests(unittest.TestCase):
    def test_normal_schedule(self): self.assertEqual(schedule(BASE)[0][0]["activities"][0]["name"], "市場")
    def test_not_duplicate(self): self.assertEqual(sum(len(x["activities"]) for x in schedule(BASE)[0]), 1)
    def test_open_weekday(self): self.assertEqual(len(schedule({**BASE, "activities": [{**BASE["activities"][0], "open_weekdays": [5]}]})[0][0]["activities"]), 0)
    def test_unplanned(self): self.assertEqual(len(schedule(BASE)[1]), 0)
    def test_budget(self): self.assertEqual(build_plan(BASE, "mock")["budget_summary"]["activities"], 100)
    def test_mock_flight(self): self.assertEqual(MockFlightProvider().search({"origin":"TPE","destination":"KIX","departure_date":"2026-10-01"})[0]["provider"], "mock")
    def test_missing_source_rejected(self):
        with self.assertRaises(ValidationError): validate_input({**BASE, "activities": [{**BASE["activities"][0], "source_url": ""}]})
    def test_reversed_dates_rejected(self):
        with self.assertRaises(ValidationError): validate_input({**BASE, "start_date": "2026-10-03"})
    def test_bad_iata_rejected(self):
        with self.assertRaises(ValidationError): validate_input({**BASE, "origin": "Taipei"})
    def test_negative_budget_rejected(self):
        with self.assertRaises(ValidationError): validate_input({**BASE, "budget": -1})
    def test_bad_types_are_validation_errors(self):
        for key, value in (("travellers", "one"), ("budget", "none"), ("currency", 1), ("interests", "food")):
            with self.subTest(key=key):
                with self.assertRaises(ValidationError): validate_input({**BASE, key: value})
    def test_invalid_activity_schema_is_validation_error(self):
        for key, value in (("latitude", "north"), ("open_weekdays", [8]), ("activities", "no")):
            with self.subTest(key=key):
                data = {**BASE, "activities": [{**BASE["activities"][0], key: value}]} if key != "activities" else {**BASE, key: value}
                with self.assertRaises(ValidationError): validate_input(data)
    def test_duffel_key_error(self):
        old = os.environ.pop("DUFFEL_ACCESS_TOKEN", None)
        try:
            with self.assertRaises(RuntimeError): DuffelFlightProvider().search({"origin":"TPE","destination":"KIX","departure_date":"2026-10-01"})
        finally:
            if old is not None: os.environ["DUFFEL_ACCESS_TOKEN"] = old
    def test_duffel_request_and_parse(self):
        response = {"data": {"offers": [{"id": "off_1", "total_amount": "100", "total_currency": "TWD", "expires_at": "2026-10-01T00:00:00Z", "owner": {"name": "Air"}, "secret": "excluded"}]}}
        with patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "test-token"}), patch("travel_assistant.providers.urlopen", return_value=Response(response)) as opener:
            offers = DuffelFlightProvider().search({"origin": "TPE", "destination": "KIX", "departure_date": "2026-10-01", "travellers": 2})
        request = opener.call_args.args[0]
        self.assertIn("return_offers=true", request.full_url)
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data)["data"]["passengers"], [{"type": "adult"}, {"type": "adult"}])
        self.assertEqual(offers, [{"provider": "duffel", "offer_id": "off_1", "total_amount": "100", "total_currency": "TWD", "expires_at": "2026-10-01T00:00:00Z", "owner": "Air"}])
    def test_skyscanner_disabled(self):
        old = os.environ.pop("SKYSCANNER_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError): SkyscannerFlightProvider().search({})
        finally:
            if old is not None: os.environ["SKYSCANNER_API_KEY"] = old
    def test_weather_success(self):
        today = date.today().isoformat()
        with patch("travel_assistant.weather.urlopen", return_value=Response({"daily": {"time": [today]}})):
            self.assertEqual(get_weather(35, 135, today, today), {"daily": {"time": [today]}})
    def test_weather_degrades_without_network(self):
        today = date.today().isoformat()
        with patch("travel_assistant.weather.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(get_weather(35, 135, today, today))
    def test_weather_degrades_out_of_range_date(self):
        future = (date.today() + timedelta(days=17)).isoformat()
        with patch("travel_assistant.weather.urlopen") as opener:
            self.assertIsNone(get_weather(35, 135, future, future))
        opener.assert_not_called()
    def test_plan_weather_and_markdown_sources(self):
        with patch("travel_assistant.cli.get_weather", return_value={"daily": {}}):
            plan = build_plan(BASE, "mock", weather=True)
        text = markdown(plan)
        self.assertEqual(plan["weather"], {"daily": {}})
        self.assertIn("source_url: https://www.kuromon.com/en/", text)
        self.assertNotIn("{'provider'", text)
    def test_markdown_nonempty_sections_omit_empty_markers(self):
        plan = build_plan(BASE, "mock")
        plan["itinerary"] = [plan["itinerary"][0]]
        text = markdown(plan)
        itinerary, flights = text.split("## 航班候選")
        self.assertNotIn("- 無安排", itinerary)
        self.assertNotIn("- 無", flights.split("## 預算摘要")[0])

    def test_markdown_empty_sections_include_one_empty_marker(self):
        plan = build_plan({**BASE, "activities": []}, "mock")
        plan["itinerary"] = [plan["itinerary"][0]]
        plan["flights"] = []
        text = markdown(plan)
        itinerary, flights = text.split("## 航班候選")
        self.assertEqual(itinerary.count("- 無安排"), 1)
        self.assertEqual(flights.split("## 預算摘要")[0].count("- 無"), 1)

    def test_weather_uses_scheduled_activity_coordinates(self):
        first = {**BASE["activities"][0], "name": "未排入", "latitude": 1, "longitude": 2, "open_weekdays": [5]}
        second = {**BASE["activities"][0], "name": "已排入", "latitude": 3, "longitude": 4, "open_weekdays": [4]}
        with patch("travel_assistant.cli.get_weather", return_value={}) as weather:
            build_plan({**BASE, "activities": [first, second]}, "mock", weather=True)
        self.assertEqual(weather.call_args.args[:2], (3, 4))

    def test_json_serializable(self): json.dumps(build_plan(BASE, "mock"), ensure_ascii=False)


if __name__ == "__main__": unittest.main()

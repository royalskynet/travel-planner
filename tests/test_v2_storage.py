import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.domain import migrate_v1
from travel_assistant.storage import SQLiteTripRepository

FIXTURE = {
    "origin": "TPE", "destination": "KIX", "start_date": "2026-10-01", "end_date": "2026-10-02",
    "travellers": 1, "budget": 5000, "currency": "TWD", "interests": [], "activities": [],
}


class StorageTests(unittest.TestCase):
    def test_revisions_are_append_only_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteTripRepository(Path(directory) / "trips.sqlite3")
            trip = migrate_v1(FIXTURE, trip_id="osaka")
            first = repository.save(trip, plan={"status": "draft"}, provider_summary={"mock": {"status": "ok"}})
            trip.title = "Osaka revised"
            second = repository.save(trip, plan={"status": "planned"})

            self.assertEqual((first, second), (1, 2))
            self.assertEqual(repository.list_revisions("osaka"), [1, 2])
            self.assertEqual(repository.get("osaka", 1).trip.title, "TPE → KIX")
            self.assertEqual(repository.get("osaka").trip.title, "Osaka revised")
            self.assertEqual(repository.get("osaka", 1).provider_summary["mock"]["status"], "ok")

    def test_missing_revision_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteTripRepository(Path(directory) / "trips.sqlite3")
            with self.assertRaises(KeyError):
                repository.get("missing")

    def test_latest_planned_skips_newer_unplanned_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteTripRepository(Path(directory) / "trips.sqlite3")
            trip = migrate_v1(FIXTURE, trip_id="osaka")
            repository.save(trip, plan={"status": "planned"})
            trip.title = "new input"
            repository.save(trip)
            record = repository.get_latest_planned("osaka")
            self.assertEqual(record.revision, 1)
            self.assertEqual(record.plan, {"status": "planned"})

    def test_repository_creates_nested_database_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "output" / "nested" / "trips.db"
            repository = SQLiteTripRepository(database)
            repository.save(migrate_v1(FIXTURE, trip_id="osaka"))
            self.assertTrue(database.is_file())


if __name__ == "__main__":
    unittest.main()

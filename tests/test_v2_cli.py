import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.cli import main


class V2CliTests(unittest.TestCase):
    def test_malformed_flight_request_is_clean_parse_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "request.json"
            request.write_text(json.dumps({"slices": []}), encoding="utf-8")
            stderr = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "travel-assistant",
                        "flight",
                        "search",
                        str(request),
                        "--provider",
                        "mock",
                    ],
                ),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(main(), 2)
            error = json.loads(stderr.getvalue())
            self.assertEqual(error["provider"], "mock")
            self.assertEqual(error["status"], "parse_error")
            self.assertIn("slices", error["error"])

    def test_fli_cli_fails_cleanly_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            request = Path(temporary) / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "slices": [
                            {
                                "origin": "TPE",
                                "destination": "KIX",
                                "departure_date": "2026-10-01",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "travel-assistant",
                        "flight",
                        "search",
                        str(request),
                        "--provider",
                        "fli-experimental",
                    ],
                ),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(main(), 2)
            error = json.loads(stderr.getvalue())
            self.assertEqual(error["provider"], "fli-experimental")
            self.assertEqual(error["status"], "unavailable")
            self.assertIn("disabled by default", error["error"])


if __name__ == "__main__":
    unittest.main()

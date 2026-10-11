import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.providers_v2 import HttpResponse, ResponseTooLargeError
from travel_assistant.research import (
    OSRMClient,
    OverpassClient,
    ResearchHttpError,
    ResearchParseError,
    UnsafeUrlError,
    validate_public_https_url,
)


def PUBLIC(host, port):
    return ["93.184.216.34"]


def PRIVATE(host, port):
    return ["127.0.0.1"]


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


class ResearchTests(unittest.TestCase):
    def test_url_guard_blocks_non_https_and_private_targets(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url("http://example.com", resolver=PUBLIC)
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url("https://127.0.0.1/service")
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url("https://example.com", resolver=PRIVATE)

    def test_url_guard_rejects_credentials_and_fragments(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url("https://user:pass@example.com", resolver=PUBLIC)
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url("https://example.com/#fragment", resolver=PUBLIC)

    def test_custom_network_endpoint_requires_injected_transport(self):
        with self.assertRaises(ValueError):
            OSRMClient("https://example.com", resolver=PUBLIC)
        with self.assertRaises(ValueError):
            OverpassClient("https://example.com/api", resolver=PUBLIC)

    def test_custom_private_endpoint_is_rejected_even_with_transport(self):
        fake = FakeTransport(HttpResponse(200, b"{}", {}))
        with self.assertRaises(UnsafeUrlError):
            OSRMClient("https://127.0.0.1", transport=fake)

    def test_osrm_matrix_is_bounded_and_parsed(self):
        payload = {
            "code": "Ok",
            "durations": [[0, 60], [60, 0]],
            "distances": [[0, 800], [800, 0]],
        }
        fake = FakeTransport(HttpResponse(200, json.dumps(payload).encode(), {}))
        client = OSRMClient(transport=fake, resolver=PUBLIC, max_coordinates=2)
        result = client.matrix([(25.03, 121.56), (25.04, 121.57)])
        self.assertEqual(result["durations"][0][1], 60)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["retrieved_at"].endswith("Z"))
        self.assertIn("121.560000,25.030000", fake.calls[0][1])
        with self.assertRaises(ValueError):
            client.matrix([(25, 121), (25.1, 121.1), (25.2, 121.2)])

    def test_osrm_429_and_parse_errors_are_loud(self):
        rate_limited = OSRMClient(
            transport=FakeTransport(HttpResponse(429, b"{}", {})), resolver=PUBLIC
        )
        with self.assertRaises(ResearchHttpError):
            rate_limited.matrix([(25, 121), (25.1, 121.1)])
        bad = OSRMClient(
            transport=FakeTransport(HttpResponse(200, b"not-json", {})), resolver=PUBLIC
        )
        with self.assertRaises(ResearchParseError):
            bad.matrix([(25, 121), (25.1, 121.1)])

    def test_injected_transport_cannot_bypass_response_size_limit(self):
        client = OSRMClient(
            transport=FakeTransport(HttpResponse(200, b"x" * 101, {})),
            resolver=PUBLIC,
            max_response_bytes=100,
        )
        with self.assertRaises(ResponseTooLargeError):
            client.matrix([(25, 121), (25.1, 121.1)])

    def test_overpass_result_count_is_capped(self):
        fake = FakeTransport(
            HttpResponse(
                200, json.dumps({"elements": [{"id": 1}, {"id": 2}]}).encode(), {}
            )
        )
        result = OverpassClient(
            transport=fake, resolver=PUBLIC, max_elements=1
        ).search_pois(25, 121)
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["provider"], "overpass")
        self.assertTrue(result["retrieved_at"].endswith("Z"))
        self.assertTrue(result["truncated"])
        self.assertIn("tourism", fake.calls[0][2]["body"].decode())

    def test_overpass_rejects_unbounded_or_injected_tags(self):
        client = OverpassClient(
            transport=FakeTransport(HttpResponse(200, b'{"elements": []}', {})),
            resolver=PUBLIC,
        )
        with self.assertRaises(ValueError):
            client.search_pois(25, 121, radius_m=50_001)
        with self.assertRaises(ValueError):
            client.search_pois(25, 121, tags={"tourism": 'x"];out;["'})


if __name__ == "__main__":
    unittest.main()

import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from travel_assistant.providers_v2 import (
    Capability,
    DuffelProvider,
    ExperimentalProviderDisabled,
    FliExperimentalProvider,
    GoogleFlightsLinkProvider,
    HttpResponse,
    HttpxTransport,
    MockFlightProvider,
    ProviderConfigurationError,
    ProviderParseError,
    ProviderStatus,
    SkyscannerProvider,
    google_flights_deep_link,
)

REQUEST = {
    "slices": [{"origin": "TPE", "destination": "KIX", "departure_date": "2026-10-01"}]
}


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def response(payload, status=200, headers=None):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return HttpResponse(status, body, headers or {})


class ProviderTests(unittest.TestCase):
    def test_mock_is_offline_multi_city_and_never_invents_price(self):
        result = MockFlightProvider().search(
            {
                "slices": [
                    {
                        "origin": "TPE",
                        "destination": "KIX",
                        "departure_date": "2026-10-01",
                    },
                    {
                        "origin": "KIX",
                        "destination": "TPE",
                        "departure_date": "2026-10-05",
                    },
                ],
                "currency": "TWD",
            }
        )
        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(len(result.items[0]["slices"]), 2)
        self.assertIsNone(result.items[0]["price"])
        self.assertFalse(result.items[0]["is_live"])

    def test_capabilities_are_explicit(self):
        self.assertTrue(DuffelProvider.capabilities.supports(Capability.MULTI_CITY))
        self.assertFalse(
            DuffelProvider.capabilities.supports(Capability.FLEXIBLE_DATES)
        )

    def test_duffel_multi_slice_payload_and_normalization(self):
        transport = ScriptedTransport(
            response(
                {
                    "data": {
                        "offers": [
                            {
                                "id": "off_1",
                                "total_amount": "120.50",
                                "total_currency": "USD",
                                "expires_at": "2026-10-01T00:00:00Z",
                                "owner": {"name": "Example Air"},
                                "slices": [
                                    {
                                        "duration": "PT2H",
                                        "segments": [
                                            {
                                                "origin": {"iata_code": "TPE"},
                                                "destination": {"iata_code": "KIX"},
                                                "departing_at": "2026-10-01T08:00:00",
                                                "arriving_at": "2026-10-01T12:00:00",
                                                "marketing_carrier": {
                                                    "iata_code": "ZZ"
                                                },
                                                "marketing_carrier_flight_number": "123",
                                            }
                                        ],
                                    }
                                ],
                                "secret": "must-not-leak",
                            }
                        ]
                    }
                },
                headers={"x-request-id": "req-1"},
            )
        )
        provider = DuffelProvider("test-token", transport=transport)
        result = provider.search(
            {
                "slices": [
                    {
                        "origin": "TPE",
                        "destination": "KIX",
                        "departure_date": "2026-10-01",
                    },
                    {
                        "origin": "KIX",
                        "destination": "TPE",
                        "departure_date": "2026-10-05",
                    },
                ],
                "travellers": 2,
            }
        )
        sent = json.loads(transport.calls[0][2]["body"])
        self.assertEqual(len(sent["data"]["slices"]), 2)
        self.assertEqual(len(sent["data"]["passengers"]), 2)
        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(result.items[0]["slices"][0]["segments"][0]["origin"], "TPE")
        self.assertNotIn("secret", result.items[0])

    def test_empty_is_not_failure(self):
        result = DuffelProvider(
            "token", transport=ScriptedTransport(response({"data": {"offers": []}}))
        ).search(
            {"origin": "TPE", "destination": "KIX", "departure_date": "2026-10-01"}
        )
        self.assertEqual(result.status, ProviderStatus.EMPTY)
        self.assertEqual(result.data, [])
        self.assertTrue(result.ok)

    def test_timeout_rate_limit_and_parse_are_distinct(self):
        request = {
            "origin": "TPE",
            "destination": "KIX",
            "departure_date": "2026-10-01",
        }
        timeout = DuffelProvider(
            "token", transport=ScriptedTransport(TimeoutError())
        ).search(request)
        rate_limit = DuffelProvider(
            "token", transport=ScriptedTransport(response({}, 429))
        ).search(request)
        parse = DuffelProvider(
            "token", transport=ScriptedTransport(response(b"not-json"))
        ).search(request)
        self.assertEqual(timeout.status, ProviderStatus.TIMEOUT)
        self.assertEqual(rate_limit.status, ProviderStatus.RATE_LIMITED)
        self.assertEqual(parse.status, ProviderStatus.PARSE_ERROR)
        self.assertIsNone(timeout.data)

    def test_invalid_duffel_price_is_parse_failure(self):
        payload = {
            "data": {
                "offers": [{"id": "bad", "total_amount": "0", "total_currency": "USD"}]
            }
        }
        result = DuffelProvider(
            "token", transport=ScriptedTransport(response(payload))
        ).search(
            {"origin": "TPE", "destination": "KIX", "departure_date": "2026-10-01"}
        )
        self.assertEqual(result.status, ProviderStatus.PARSE_ERROR)

    def test_httpx_transport_refuses_redirects(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(
                302, headers={"location": "https://127.0.0.1/private"}
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler), follow_redirects=True
        )
        try:
            result = HttpxTransport(client).request(
                "GET", "https://example.com", timeout=1, max_bytes=100
            )
        finally:
            client.close()
        self.assertEqual(result.status_code, 302)
        self.assertEqual(calls, ["https://example.com"])

    def test_duffel_without_key_fails_loud(self):
        previous = os.environ.pop("DUFFEL_ACCESS_TOKEN", None)
        try:
            with self.assertRaises(ProviderConfigurationError):
                DuffelProvider().search(
                    {
                        "origin": "TPE",
                        "destination": "KIX",
                        "departure_date": "2026-10-01",
                    }
                )
        finally:
            if previous is not None:
                os.environ["DUFFEL_ACCESS_TOKEN"] = previous

    def test_skyscanner_gate_and_missing_key(self):
        with self.assertRaises(ProviderConfigurationError):
            SkyscannerProvider(api_key="key", enabled=False).search(REQUEST)
        previous = os.environ.pop("SKYSCANNER_API_KEY", None)
        try:
            with self.assertRaises(ProviderConfigurationError):
                SkyscannerProvider(enabled=True).search(REQUEST)
        finally:
            if previous is not None:
                os.environ["SKYSCANNER_API_KEY"] = previous

    def test_skyscanner_running_then_complete(self):
        transport = ScriptedTransport(
            response(
                {"sessionToken": "session/1", "status": "RESULT_STATUS_INCOMPLETE"}
            ),
            response(
                {
                    "status": "RESULT_STATUS_COMPLETE",
                    "content": {"results": {"itineraries": {"it-1": {"id": "it-1"}}}},
                }
            ),
        )
        result = SkyscannerProvider(
            "key", enabled=True, transport=transport, max_polls=1
        ).search({**REQUEST, "query": {}})
        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(result.items[0]["id"], "it-1")
        self.assertIn("session%2F1", transport.calls[1][1])

    def test_skyscanner_poll_exhaustion(self):
        transport = ScriptedTransport(
            response({"sessionToken": "session", "status": "RESULT_STATUS_INCOMPLETE"}),
            response({"status": "RESULT_STATUS_INCOMPLETE"}),
            response({"status": "RESULT_STATUS_INCOMPLETE"}),
        )
        result = SkyscannerProvider(
            "key", enabled=True, transport=transport, max_polls=2
        ).search({**REQUEST, "query": {}})
        self.assertEqual(result.status, ProviderStatus.TIMEOUT)
        self.assertEqual(len(transport.calls), 3)

    def test_google_deep_link_is_deterministic_and_not_live(self):
        request = {
            "slices": [
                {"origin": "TPE", "destination": "KIX", "departure_date": "2026-10-01"},
                {"origin": "KIX", "destination": "TPE", "departure_date": "2026-10-05"},
            ],
            "currency": "TWD",
            "language": "zh-TW",
        }
        url = google_flights_deep_link(request)
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parse_qs(parsed.query)["curr"], ["TWD"])
        result = GoogleFlightsLinkProvider().search(request)
        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertFalse(result.items[0]["is_live"])

    def test_fli_defaults_to_hard_rejection(self):
        with self.assertRaises(ExperimentalProviderDisabled):
            FliExperimentalProvider().search(REQUEST)
        with self.assertRaises(ProviderConfigurationError):
            FliExperimentalProvider(enabled=True).search(REQUEST)

    def test_all_providers_reject_malformed_request_before_other_gates(self):
        providers = [
            MockFlightProvider(),
            DuffelProvider(),
            SkyscannerProvider(),
            GoogleFlightsLinkProvider(),
            FliExperimentalProvider(),
        ]
        invalid_requests = [
            {},
            {"slices": []},
            {"slices": [{"origin": "TPE"}]},
            {
                "slices": [
                    {
                        "origin": "tpe",
                        "destination": "KIX",
                        "departure_date": "2026-10-01",
                    }
                ]
            },
            {
                "slices": [
                    {
                        "origin": "TPE",
                        "destination": "KIX",
                        "departure_date": "2026-02-30",
                    }
                ]
            },
            {
                "slices": [
                    {
                        "origin": "TPE",
                        "destination": "KIX",
                        "departure_date": "2026-10-05",
                    },
                    {
                        "origin": "KIX",
                        "destination": "TPE",
                        "departure_date": "2026-10-01",
                    },
                ]
            },
            {**REQUEST, "adults": -1},
            {**REQUEST, "adults": True},
            {**REQUEST, "adults": 0, "children": 0, "infants": 0},
            {**REQUEST, "adults": 1, "infants": 2},
            {**REQUEST, "adults": 10},
            {**REQUEST, "cabin_class": "private_jet"},
            {**REQUEST, "currency": "usd"},
            {
                "slices": [
                    {
                        "origin": "TPE",
                        "destination": "KIX",
                        "departure_date": "2026-10-01",
                    },
                    {
                        "origin": "KIX",
                        "destination": "TPE",
                        "departure_date": "2026-10-01",
                    },
                ]
            },
        ]
        for provider in providers:
            for request in invalid_requests:
                with (
                    self.subTest(provider=provider.name, request=request),
                    self.assertRaises(ProviderParseError),
                ):
                    provider.search(request)


if __name__ == "__main__":
    unittest.main()

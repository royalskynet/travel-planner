from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen


def get_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> dict | None:
    try:
        if isinstance(latitude, bool) or isinstance(longitude, bool) or not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
            return None
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if start > end or start < date.today() - timedelta(days=1) or start > date.today() + timedelta(days=16):
            return None
        params = urlencode({"latitude": latitude, "longitude": longitude, "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max", "start_date": start_date, "end_date": end_date, "timezone": "auto"})
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=10) as response:
            return json.load(response)
    except (OSError, TypeError, ValueError):
        return None
